"""The Bot at work: it sits at a desk and acts out what your coding agent is doing."""
import math
import random
import secrets
import shutil
import struct
import subprocess
import threading
import time

from .theme import BG, BODY, co_ease, co_mix, LINE, MUTED, ROW, TEXT, WARN


# ---- the Bot at work: it sits at a desk and acts out your coding agent ----------------------------------
# Your coding agent says what it's doing through the web page (webui.py passes it on): Claude Code's
# hooks (coder_hooks.py sets them up), or POST /coder?pose=typing from anything else. A WAV sent to
# POST /coder/say is said out loud while it moves its mouth.
CODER_POSES = ("rest", "typing", "reading", "thinking", "talking", "done", "hello", "attention",
               "error", "shrug", "wake", "sleep")
CODER_BUSY = ("typing", "reading", "thinking", "talking")      # these keep going until something else comes
CODER_ONCE = {"done": 1.6, "hello": 2.8, "shrug": 2.4, "wake": 3.0, "sleep": 2.2}   # seconds, then it rests
CODER_WAIT = {"attention": 60, "error": 60}      # held this long, then it rests
CODER_HOLD = 1.0           # seconds each pose shows at least (one asked for meanwhile waits: the last one)
CODER_STUCK = 300          # busy this long without a word from the agent: it asks for you
CODER_NAP = 600            # nothing happening this long: it nods off
CODER_EASE = 0.3           # seconds it takes to move from one pose to the next
CODER_SAY_AS = ("talking", "typing", "reading", "thinking", "rest")   # the poses a clip can be said in
CODER_CLIP_MAX = 8 << 20   # bytes: a clip an agent sends to be said (a few minutes of speech)
CODER_RATE = 22050         # its own sounds
CODER_SOUND_AT = {"done": 0.38, "hello": 0.15, "attention": 0.2, "error": 0.1, "shrug": 0.3}   # (seconds in)
CODER_FPS = {"typing": 8, "reading": 6, "thinking": 6, "talking": 10, "done": 10, "hello": 10,   # frames a
             "attention": 6, "error": 6, "shrug": 8, "wake": 8, "sleep": 8, "rest": 6}  # second
CODER_TITLES = {"typing": "Typing", "reading": "Reading", "thinking": "Thinking", "talking": "Talking",
                "hello": "Hello", "attention": "Needs you", "error": "Something went wrong",
                "shrug": "Oh well", "wake": "Waking up", "sleep": "Falling asleep"}
CODER_TOKENS = ["{ }", "</>", "=>", "( )", ";", "[ ]", "fn", "if", "+=", "#", "::", "&&"]

# where things are on its desk (screen pixels, on the GPi Case's 640x480: a bigger screen has them in
# the middle, the desk at the foot)
CO_X = 320                       # the coder's middle
CO_TOP = 374                     # the desk's top
CO_BOX = (196, 84, 500, 382)     # where it moves: drawn twice as big and halved, for smooth edges
CO_DIRTY = (100, 69, 548, 384)   # what changes from one frame to the next (the rest is sent when it changes)
CO_SHOULDERS = ((268, 270), (372, 270))
CO_ARM = (56, 54, 9)             # upper arm, forearm, half its width
CO_REST = ((232, 366), (408, 366))          # hands on the desk
CO_KEYS = ((298, 338), (342, 338))          # ...on the keyboard, behind the laptop's lid
CO_BELL = (466, 318)             # the top of the bell's button
CO_LID = (252, 290, 388, 377)
# ...and its colours (the eyes and the light on its antenna are the accent colour)
CO_SHELL, CO_SHADE, CO_JOINT = (220, 225, 232), (184, 191, 202), (146, 154, 167)
CO_FACE = (12, 14, 18)
CO_LID_FILL, CO_LID_EDGE = (54, 61, 74), (82, 90, 106)
CO_DESK, CO_DESK_EDGE, CO_DESK_FRONT = (74, 67, 62), (96, 87, 80), (40, 37, 36)
CO_BRASS, CO_BRASS_DARK, CO_BRASS_LIGHT = (212, 170, 82), (150, 114, 48), (246, 224, 160)
CO_MUG = (84, 120, 136)


def co_lerp(a, b, f):
    return a + (b - a) * f


def co_noise(seed, i):
    """The same number from 0 to 1 for the same seed and i: a little randomness with nothing to keep."""
    return (math.sin(i * 12.9898 + seed * 78.233) * 43758.5453) % 1.0


def co_between(t, t0, t1):
    """0 before t0, 1 after t1, eased in between."""
    return co_ease((t - t0) / (t1 - t0)) if t1 > t0 else float(t >= t1)


def co_towards(p, q, f):
    return (co_lerp(p[0], q[0], f), co_lerp(p[1], q[1], f))


def co_ik(s, target, l1, l2, prefer):
    """(elbow, hand) for an arm from shoulder s reaching for target (or as near as it can get).
    prefer: the elbow 'out' (away from its body), 'down' or 'up'."""
    dx, dy = target[0] - s[0], target[1] - s[1]
    d = math.hypot(dx, dy) or 1e-3
    d2 = max(abs(l1 - l2) + 0.5, min(d, l1 + l2 - 0.5))
    ux, uy = dx / d, dy / d
    hand = (s[0] + ux * d2, s[1] + uy * d2)
    a = (l1 * l1 - l2 * l2 + d2 * d2) / (2 * d2)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    px, py = s[0] + ux * a, s[1] + uy * a
    e1, e2 = (px - uy * h, py + ux * h), (px + uy * h, py - ux * h)
    if prefer == "down":
        return (e1 if e1[1] >= e2[1] else e2), hand
    if prefer == "up":
        return (e1 if e1[1] <= e2[1] else e2), hand
    return (e1 if abs(e1[0] - CO_X) >= abs(e2[0] - CO_X) else e2), hand


def co_blink(T, seed, period=4.2):
    """Its eyelids: 1 open, 0 shut. A blink every few seconds, now and then two."""
    k = math.floor(T / period)
    lid = 1.0
    for kk in (k - 1, k):
        start = kk * period + 0.3 + co_noise(seed, kk) * (period - 0.9)
        for extra in ((0.0, 0.28) if co_noise(seed, kk + 77) > 0.78 else (0.0,)):
            u = T - start - extra
            if 0 <= u < 0.17:
                lid = min(lid, 0.08 + 0.92 * abs(math.cos(math.pi * u / 0.17)))
    return lid


def co_glance(T, seed, period=7.5):
    """Now and then it looks to one side for a moment."""
    k = math.floor(T / period)
    r = co_noise(seed, k + 31)
    if r < 0.45:
        return 0.0
    u = T - k * period
    return (-1 if r < 0.72 else 1) * 0.75 * co_between(u, 2.0, 2.35) * (1 - co_between(u, 3.6, 3.95))


def coder_pose(anim, t, T, asleep=False, energy=None, seed=0.0):
    """How it looks t seconds into a pose (T: a clock that keeps going, for blinking and breathing;
    energy: how loud the clip it's saying is just now, or None when there isn't one). Screen pixels;
    its eyes look -1 to 1 each way."""
    p = {"head": [0.0, 1.4 * math.sin(T * 2 * math.pi / 3.8)], "look": [co_glance(T, seed), 0.0],
         "lid": co_blink(T, seed), "eyes": "open", "size": 1.0, "mouth": None, "light": ("dim", 0.0),
         "hands": [CO_REST[0], CO_REST[1]], "front": [False, False], "elbow": ["out", "out"],
         "bubble": None, "bell": 0.0, "dings": None, "dim": 0.0, "tokens": False, "zzz": False}
    if asleep and anim in ("rest", "sleep"):
        p.update(eyes="shut", lid=0.0, dim=0.55, look=[0.0, 0.3], light=("off", 0.0), zzz=True)
        p["head"][1] = 11 + 2.0 * math.sin(T * 2 * math.pi / 5.0)
    elif anim == "typing":
        p["look"] = [0.22 * math.sin(T * 1.3), 0.6]
        p["lid"] = min(p["lid"], 0.86)
        p["head"][1] = 3 + 1.2 * math.sin(T * 2 * math.pi * 1.1)
        for i, (x, y) in enumerate(CO_KEYS):
            u = T * 2.7 + i * 0.5 + 0.2 * co_noise(seed, math.floor(T * 2.7) * 2 + i)
            lift = max(0.0, math.sin(2 * math.pi * u)) ** 2
            p["hands"][i] = (x + 5 * math.sin(T * 0.8 + i * 2), y - 8 * lift)
        p.update(light=("busy", 1.0), tokens=True)
    elif anim == "reading":
        line = math.floor(T / 1.7)
        u = T - line * 1.7
        sweep = -0.65 + 1.3 * co_between(u, 0.05, 1.35) if u < 1.4 else 0.65 - 1.3 * co_between(u, 1.4, 1.62)
        p["look"] = [sweep, 0.35 + 0.08 * (line % 3)]
        p["head"] = [sweep * 3, 2.5]
        tap = co_between(u, 1.38, 1.46) * (1 - co_between(u, 1.48, 1.6))
        p["hands"] = [CO_KEYS[0], (CO_KEYS[1][0] + 4, CO_KEYS[1][1] - 6 * tap)]
        p.update(light=("busy", 1.0), bubble=("doc", line % 5))
    elif anim == "thinking":
        side = 1 if math.floor(T / 6.0) % 3 != 2 else -1
        p["look"] = [side * (0.55 + 0.2 * math.sin(T * 0.6)), -0.72 + 0.08 * math.sin(T * 0.9)]
        p["head"] = [side * 3.0, -2.0 + 1.0 * math.sin(T * 2 * math.pi / 4.0)]
        p["lid"] = min(p["lid"], 0.92)
        k = T % 5.0
        scratch = 3 * math.sin(T * 2 * math.pi * 3.2) * co_between(k, 1.0, 1.2) * (1 - co_between(k, 2.0, 2.2))
        p["hands"][1] = (403 + p["head"][0], 194 + p["head"][1] + scratch)    # a hand at the side of its head
        p["front"][1] = True
        p.update(light=("busy", 0.75 + 0.25 * math.sin(T * 2.4)), bubble=("think", T))
    elif anim == "talking":
        e = energy
        if e is None:                              # (no clip: it chats away as if there were one)
            e = (0.25 + 0.75 * co_noise(seed, math.floor(T * 4.2))) * math.sin(math.pi * ((T * 4.2) % 1)) ** 0.7
            if co_noise(seed, math.floor(T / 2.2) + 300) < 0.3:
                e *= 0.15
        p["mouth"], p["size"] = e, 1.06
        p["look"] = [p["look"][0] * (1 - min(1.0, e * 3)), -0.05]
        p["head"][1] += -2.5 * e
        k = T % 3.0
        lift = co_between(co_noise(seed, math.floor(T / 3.0) + 500), 0.55, 0.75) \
            * co_between(k, 0.2, 0.6) * (1 - co_between(k, 1.6, 2.1))
        p["hands"][1] = co_towards(CO_REST[1], (404, 292), lift)
        p["front"][1] = lift > 0.05
        p.update(light=("busy", 0.7 + 0.3 * min(1.0, e * 2)), bubble=("waves", e))
    elif anim == "done":
        up, hit = (CO_BELL[0], CO_BELL[1] - 26), (CO_BELL[0], CO_BELL[1] - 9)
        if t < 0.32:
            h = co_towards(CO_REST[1], up, co_between(t, 0.0, 0.3))
        elif t < 0.4:
            h = co_towards(up, hit, co_between(t, 0.32, 0.38))
        elif t < 0.75:
            h = co_towards(hit, (up[0] - 2, up[1] + 8), co_between(t, 0.4, 0.62))
        else:
            h = co_towards((up[0] - 2, up[1] + 8), CO_REST[1], co_between(t, 0.85, 1.45))
        p["hands"][1] = h
        p["front"][1] = True
        p["elbow"][1] = "up"
        p["look"] = [0.85, 0.55] if t < 0.5 else [0.2 * (1 - co_between(t, 0.5, 0.9)), 0.0]
        if t >= 0.42:
            p["eyes"] = "happy"
        if t >= 0.38:
            p.update(bell=max(0.0, 1 - (t - 0.38) / 0.9), dings=t - 0.38,
                     light=("flash", 1.0 - co_between(t, 0.38, 1.4) * 0.5))
        else:
            p["light"] = ("flash", 0.6)
    elif anim == "hello":
        raised = co_between(t, 0.0, 0.45) * (1 - co_between(t, 2.2, 2.75))
        wave = 15 * math.sin((t - 0.45) * 2 * math.pi * 2.4) * co_between(t, 0.45, 0.6) * (1 - co_between(t, 1.9, 2.2))
        p["hands"][1] = co_towards(CO_REST[1], (414 + wave, 188), raised)
        p["front"][1] = raised > 0.05
        p["elbow"][1] = "down"
        p["eyes"] = "happy" if 0.25 < t < 2.6 else "open"
        p["head"][1] += -3 * math.sin(math.pi * co_between(t, 0.5, 0.9)) - 3 * math.sin(math.pi * co_between(t, 1.4, 1.8))
        p["look"] = [0.0, -0.05]
        p.update(bubble=("hi", t) if 0.3 < t < 2.5 else None, light=("flash", 0.8))
    elif anim == "attention":
        if t < 10:
            raised = co_between(t, 0.0, 0.5) * (1 - co_between(t, 4.0, 4.6))
        else:
            k = t % 10.0
            raised = co_between(k, 0.0, 0.4) * (1 - co_between(k, 1.6, 2.1))
        wave = 6 * math.sin(t * 2 * math.pi * 1.8) * raised
        p["hands"][1] = co_towards(CO_REST[1], (406 + wave, 206), raised)
        p["front"][1] = raised > 0.05
        p["elbow"][1] = "down"
        p["look"] = [p["look"][0] * 0.3, -0.12]
        p["head"][1] += -1.5
        p.update(size=1.12, light=("alert", t), bubble=("bang", t))
    elif anim == "error":
        up = co_between(t, 0.0, 0.35) * (1 - co_between(t, 2.6, 3.2))
        p["hands"] = [co_towards(CO_REST[0], (240, 190), up), co_towards(CO_REST[1], (400, 190), up)]
        p["front"] = [up > 0.05, up > 0.05]
        p["elbow"] = ["down", "down"]
        p["head"][0] = 4 * math.sin(t * 2 * math.pi * 2.6) * (1 - co_between(t, 0.3, 1.6))
        if t > 3.2:                                # now and then a worried look at the laptop
            k = (t - 3.2) % 7.0
            p["look"] = [0.0, 0.55 * co_between(k, 3.0, 3.4) * (1 - co_between(k, 4.6, 5.0))]
        p.update(eyes="worried", light=("alert", t), bubble=("warn", t))
    elif anim == "shrug":
        s = co_between(t, 0.0, 0.4) * (1 - co_between(t, 1.8, 2.35))
        bob = 3 * math.sin(math.pi * co_between(t, 0.55, 0.85))
        p["hands"] = [co_towards(CO_REST[0], (214, 262 - bob), s), co_towards(CO_REST[1], (426, 262 - bob), s)]
        p["front"] = [s > 0.05, s > 0.05]
        p["elbow"] = ["down", "down"]
        p.update(eyes="meh", look=[-0.55 * s, 0.1], head=[-3 * s, 2 * s - bob * 0.6], light=("warn", 0.6))
    elif anim == "wake":
        lid = co_between(t, 0.0, 1.4) ** 1.5
        p["lid"] = min(lid, co_blink(T, seed)) if t > 1.5 else lid
        for b in (1.8, 2.35):
            u = t - b
            if 0 <= u < 0.17:
                p["lid"] = 0.08 + 0.92 * abs(math.cos(math.pi * u / 0.17))
        p["head"][1] = 11 * (1 - co_between(t, 0.2, 1.4))
        st = co_between(t, 1.0, 1.5) * (1 - co_between(t, 2.2, 2.8))      # a good stretch
        p["hands"] = [co_towards(CO_REST[0], (226, 150), st), co_towards(CO_REST[1], (414, 150), st)]
        p["front"] = [st > 0.05, st > 0.05]
        p.update(dim=0.55 * (1 - co_between(t, 0.0, 1.0)), light=("dim", co_between(t, 0.0, 1.4)))
    elif anim == "sleep":
        if t < 0.7:
            lid = 1 - 0.8 * co_between(t, 0.0, 0.7)
        elif t < 1.1:
            lid = 0.2 + 0.3 * co_between(t, 0.7, 1.1)              # (it fights it a little)
        else:
            lid = 0.5 * (1 - co_between(t, 1.1, 2.0))
        p["lid"] = lid
        p["head"][1] = 11 * co_between(t, 0.7, 2.0)
        p.update(dim=0.55 * co_between(t, 1.1, 2.0), light=("dim", 1 - co_between(t, 0.6, 1.8)))
    return p


def coder_blend(a, b, f):
    """Part of the way from pose a to pose b: what moves smoothly moves; the rest is b's already."""
    out = dict(b)
    out["head"] = [co_lerp(a["head"][i], b["head"][i], f) for i in (0, 1)]
    out["look"] = [co_lerp(a["look"][i], b["look"][i], f) for i in (0, 1)]
    out["hands"] = [co_towards(a["hands"][i], b["hands"][i], f) for i in (0, 1)]
    out["front"] = [a["front"][i] if f < 0.35 else b["front"][i] for i in (0, 1)]   # (an arm crosses the lid's edge)
    out["lid"] = co_lerp(a["lid"], b["lid"], f) if a["eyes"] == b["eyes"] else b["lid"]
    out["dim"] = co_lerp(a["dim"], b["dim"], f)
    out["size"] = co_lerp(a["size"], b["size"], f)
    return out


def co_light(light, accent):
    """The light on its antenna."""
    kind, v = light
    off = (58, 63, 72)
    v = v if kind == "alert" else max(0.0, min(1.0, v))
    if kind == "dim":
        return co_mix(off, co_mix(accent, CO_FACE, 0.45), v)
    if kind == "busy":
        return co_mix(co_mix(accent, CO_FACE, 0.3), accent, v)
    if kind == "flash":
        return co_mix(accent, (255, 255, 255), v * 0.55)
    if kind == "alert":                            # a slow pulse: up, hold, down
        u = (v % 1.5) / 1.5
        return co_mix(co_mix(WARN, CO_FACE, 0.75), WARN, u * 3 if u < 1 / 3 else 1.0 if u < 2 / 3 else 3 * (1 - u))
    if kind == "warn":
        return co_mix(WARN, CO_FACE, 0.2)
    return off


def coder_desk(img, ox=0, oy=0, bottom=None):
    """The desk and the mug on it (what doesn't move). ox, oy: where its 640x480 start, on a bigger screen. bottom:
    how far down its front goes (down to the buttons, unless it's said)."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    top = CO_TOP + oy
    d.rectangle((0, top, img.width, top + 8), fill=CO_DESK)
    d.line((0, top, img.width, top), fill=CO_DESK_EDGE, width=2)
    d.rectangle((0, top + 8, img.width, img.height - 49 if bottom is None else bottom), fill=CO_DESK_FRONT)
    d.rounded_rectangle((ox + 128, oy + 338, ox + 160, top + 2), radius=6, fill=CO_MUG)
    d.arc((ox + 114, oy + 346, ox + 136, oy + 366), 90, 270, fill=CO_MUG, width=5)
    d.rectangle((ox + 131, oy + 341, ox + 157, oy + 345), fill=co_mix(CO_MUG, (255, 255, 255), 0.18))


def coder_under(img):
    """What's behind the coder, twice as big: what coder_draw starts from (the same every frame)."""
    from PIL import Image
    x0, y0, x1, y1 = CO_BOX
    return img.crop(CO_BOX).resize(((x1 - x0) * 2, (y1 - y0) * 2), Image.NEAREST)


def coder_draw(img, p, accent, T, under=None):
    """The coder, its laptop and its bell, onto img (desk drawn already): twice as big, then halved,
    for smooth edges. under: coder_under(img), made once."""
    from PIL import ImageDraw
    x0, y0, x1, y1 = CO_BOX
    K = 2
    layer = (under or coder_under(img)).copy()
    d = ImageDraw.Draw(layer)

    def P(x, y):
        return ((x - x0) * K, (y - y0) * K)

    def B(a, b, c, e):
        return ((a - x0) * K, (b - y0) * K, (c - x0) * K, (e - y0) * K)

    def rr(box, r, fill):
        """A rounded rectangle: two boxes and four circles (much quicker than PIL's own corners)."""
        a, b, c, e = B(*box)
        r = max(0.0, min(r * K, (c - a) / 2, (e - b) / 2))
        if r < 1:
            d.rectangle((a, b, c, e), fill=fill)
            return
        d.rectangle((a + r, b, c - r, e), fill=fill)
        d.rectangle((a, b + r, c, e - r), fill=fill)
        for cx, cy in ((a + r, b + r), (c - r, b + r), (a + r, e - r), (c - r, e - r)):
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)

    def disc(cx, cy, r, fill):
        d.ellipse(B(cx - r, cy - r, cx + r, cy + r), fill=fill)

    def limb(a, b, w, fill):
        d.line([P(*a), P(*b)], fill=fill, width=int(w * 2 * K))
        disc(a[0], a[1], w, fill)
        disc(b[0], b[1], w, fill)

    hx, hy = p["head"]
    dim = p["dim"] * 0.35
    shell, shade, joint = co_mix(CO_SHELL, BG, dim), co_mix(CO_SHADE, BG, dim), co_mix(CO_JOINT, BG, dim)

    # the bell, on the desk to its right
    bx = CO_BELL[0]
    wob = p["bell"] * 1.6 * math.sin(T * 2 * math.pi * 14)
    push = 3 if p["dings"] is not None and p["dings"] < 0.08 else 0
    rr((bx - 28, 366, bx + 28, 377), 4, (34, 33, 34))
    d.pieslice(B(bx - 24 + wob, 334, bx + 24 + wob, 382), 180, 360, fill=CO_BRASS)
    d.arc(B(bx - 17 + wob, 340, bx + 11 + wob, 376), 200, 250, fill=CO_BRASS_LIGHT, width=3 * K)
    rr((bx - 27 + wob, 355, bx + 27 + wob, 362), 3, CO_BRASS_DARK)
    rr((bx - 2, 322 + push, bx + 2, 336), 1, CO_BRASS_DARK)
    d.ellipse(B(bx - 6, 316 + push, bx + 6, 325 + push), fill=CO_BRASS)

    # its body and head
    rr((262, 250 + hy * 0.3, 378, 352), 28, shell)
    rr((306, 232 + hy, 334, 258 + hy * 0.3), 6, joint)
    cx = CO_X + hx
    rr((cx - 2, 104 + hy, cx + 2, 126 + hy), 2, joint)                # its antenna, and the light on it
    disc(cx, 100 + hy, 7, co_light(p["light"], accent))
    rr((cx - 88, 164 + hy, cx - 74, 200 + hy), 5, shade)
    rr((cx + 74, 164 + hy, cx + 88, 200 + hy), 5, shade)
    rr((cx - 78, 128 + hy, cx + 78, 240 + hy), 32, shade)
    rr((cx - 78, 124 + hy, cx + 78, 234 + hy), 32, shell)
    rr((cx - 64, 138 + hy, cx + 64, 222 + hy), 22, CO_FACE)

    # its eyes (and a mouth while it talks)
    eye = co_mix(co_mix(accent, (255, 255, 255), 0.12), CO_FACE, p["dim"])
    glow = co_mix(eye, CO_FACE, 0.78)
    lx, ly = p["look"]
    ew, eh = 26 * p["size"], 34 * p["size"]
    for side in (-1, 1):
        ex, ey = cx + side * 23 + lx * 12, 181 + hy + ly * 11
        kind = p["eyes"]
        if kind == "happy":
            d.arc(B(ex - 13, ey - 8, ex + 13, ey + 16), 200, 340, fill=eye, width=6 * K)
        elif kind == "shut":
            d.arc(B(ex - 12, ey - 10, ex + 12, ey + 6), 20, 160, fill=eye, width=4 * K)
        elif kind == "meh":
            rr((ex - ew / 2, ey - 3, ex + ew / 2, ey + 6), 4, eye)
        else:
            h = max(eh * p["lid"], 4)
            rr((ex - ew / 2 - 3, ey - h / 2 - 3, ex + ew / 2 + 3, ey + h / 2 + 3), min(ew, h) / 2.2 + 3, glow)
            rr((ex - ew / 2, ey - h / 2, ex + ew / 2, ey + h / 2), min(ew, h) / 2.2, eye)
            if kind == "worried":                  # the outer corners come down
                outer = ex + side * (ew / 2 + 4)
                d.polygon([P(outer, ey - h / 2 - 5), P(ex - side * (ew / 2 + 4), ey - h / 2 - 5),
                           P(outer, ey - h / 2 + 13)], fill=CO_FACE)
    if p["mouth"] is not None:
        mh = 3 + 13 * max(0.0, min(1.0, p["mouth"]))
        rr((cx - 10, 210 + hy - mh / 2, cx + 10, 210 + hy + mh / 2), min(20, mh) / 2, eye)

    # its arms: the ones behind the laptop's lid, the lid, then the ones in front of it
    arms = []
    for i in (0, 1):
        s = (CO_SHOULDERS[i][0] + hx * 0.2, CO_SHOULDERS[i][1] + hy * 0.3)
        elbow, hand = co_ik(s, p["hands"][i], CO_ARM[0], CO_ARM[1], p["elbow"][i])
        arms.append((p["front"][i], s, elbow, hand))

    def arm(s, elbow, hand):
        limb(s, elbow, CO_ARM[2], shell)
        limb(elbow, hand, CO_ARM[2] - 1, shell)
        disc(elbow[0], elbow[1], 5, joint)
        disc(hand[0], hand[1], 11, shell)
        disc(hand[0], hand[1], 8, shade)
    for front, s, elbow, hand in arms:
        if not front:
            arm(s, elbow, hand)
    rr(CO_LID, 9, CO_LID_FILL)
    d.line([P(CO_LID[0] + 9, CO_LID[1] + 1), P(CO_LID[2] - 9, CO_LID[1] + 1)], fill=CO_LID_EDGE, width=2 * K)
    mx, my = (CO_LID[0] + CO_LID[2]) / 2, (CO_LID[1] + CO_LID[3]) / 2
    d.ellipse(B(mx - 9, my - 9, mx + 9, my + 9), outline=CO_LID_EDGE, width=2 * K)
    for front, s, elbow, hand in arms:
        if front:
            arm(s, elbow, hand)
    img.paste(layer.reduce(K), (x0, y0))


def coder_extras(img, p, T, accent, fonts):
    """What's drawn at the screen's own size: steam off the mug, code flying out of the laptop,
    bubbles, the bell's ring, z's."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    for k in range(2):                             # steam
        prev = None
        for j in range(14):
            y = 333 - j * 3
            x = 139 + k * 10 + 2.6 * math.sin(j * 0.55 - T * 2.2 + k * 2.0) * (0.4 + j / 14)
            c = co_mix((84, 92, 104), BG, min(1.0, 0.25 + j / 14 * 0.75 + 0.15 * math.sin(T * 0.7 + k)))
            if prev:
                d.line([prev, (x, y)], fill=c, width=2)
            prev = (x, y)
    if p["tokens"]:                                # code flying out of the laptop as it types
        for k in range(5):
            age = (T + k * 0.38) % 1.9 / 1.9
            n = math.floor((T + k * 0.38) / 1.9) * 5 + k
            side = -1 if co_noise(3, n) < 0.5 else 1
            x = co_lerp(CO_X + side * 62, CO_X + side * (110 + 70 * co_noise(5, n)), co_ease(age))
            y = 292 - 88 * age - 14 * math.sin(age * math.pi) * co_noise(7, n)
            c = co_mix(co_mix(accent, (255, 255, 255), 0.2), BG, max(0.0, age - 0.3) / 0.7)
            d.text((x, y), CODER_TOKENS[int(co_noise(9, n) * len(CODER_TOKENS))], font=fonts["code"], fill=c, anchor="mm")
    b = p["bubble"]
    kind = b[0] if b else ""
    if kind == "think":                            # a thought bubble, its dots taking turns
        for cx, cy, r in ((408, 128, 4), (420, 114, 6)):
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ROW)
        d.rounded_rectangle((428, 76, 528, 116), radius=20, fill=ROW)
        for k in range(3):
            c = TEXT if math.floor(b[1] * 2.5) % 4 == k else MUTED
            d.ellipse((456 + k * 16, 92, 464 + k * 16, 100), fill=c)
    elif kind == "doc":                            # a page, the line it's on lit up
        x0, y0 = 432, 82 + 2 * math.sin(T * 1.6)
        d.polygon([(x0, y0), (x0 + 38, y0), (x0 + 50, y0 + 12), (x0 + 50, y0 + 62), (x0, y0 + 62)], fill=ROW)
        d.polygon([(x0 + 38, y0), (x0 + 38, y0 + 12), (x0 + 50, y0 + 12)], fill=LINE)
        for k in range(5):
            y = y0 + 20 + k * 8
            d.rounded_rectangle((x0 + 8, y - 2, x0 + 8 + (34 if k < 4 else 20), y + 1), radius=1,
                                fill=accent if k == b[1] else MUTED)
    elif kind == "waves":                          # its voice
        for k, r in enumerate((16, 26, 36)):
            c = co_mix(BG, accent, max(0.0, min(1.0, b[1] * 1.6 - k * 0.3)))
            d.arc((402 - r, 182 - r, 402 + r, 182 + r), -38, 38, fill=c, width=3)
    elif kind == "hi":
        pop = co_between(b[1], 0.3, 0.45)
        w, h = 56 * pop + 4, 34 * pop + 2
        cx, cy = 196, 112
        d.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), radius=h / 2, fill=ROW)
        d.polygon([(cx + 14, cy + h / 2 - 2), (cx + 30, cy + h / 2 + 12), (cx + 4, cy + h / 2 - 2)], fill=ROW)
        if pop > 0.8:
            d.text((cx, cy), "Hi!", font=fonts["mark"], fill=TEXT, anchor="mm")
    elif kind == "bang":                           # it needs you
        r = 21 + 2 * math.sin(b[1] * 2 * math.pi / 1.5)
        cx, cy = 194, 112
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WARN)
        d.polygon([(cx + 10, cy + r - 6), (cx + 28, cy + r + 10), (cx + 18, cy + r - 12)], fill=WARN)
        d.text((cx, cy + 1), "!", font=fonts["mark"], fill=BG, anchor="mm")
    elif kind == "warn":                           # something went wrong
        s = 1 + 0.05 * math.sin(b[1] * 2 * math.pi / 1.5)
        cx, cy = 472, 104
        d.polygon([(cx, cy - 26 * s), (cx + 29 * s, cy + 22 * s), (cx - 29 * s, cy + 22 * s)], fill=WARN)
        d.text((cx, cy + 6), "!", font=fonts["mark"], fill=BG, anchor="mm")
    if p["dings"] is not None:                     # the bell rings
        for k in range(2):
            v = p["dings"] - k * 0.22
            if 0 <= v < 0.9:
                r = 26 + v * 40
                c = co_mix(CO_BRASS_LIGHT, BG, v / 0.9)
                box = (CO_BELL[0] - r, 348 - r, CO_BELL[0] + r, 348 + r)
                d.arc(box, 205, 245, fill=c, width=3)
                d.arc(box, 295, 335, fill=c, width=3)
    if p["zzz"]:
        for k in range(3):
            age = ((T + k * 1.1) % 3.3) / 3.3
            d.text((408 + 26 * age + 6 * math.sin(age * 6), 150 - 64 * age), "z",
                   font=fonts["z"][min(2, int(age * 3))], fill=co_mix(BODY, BG, age), anchor="mm")


CODER_SOUNDS = {}


def coder_sound(name):
    """One of its own sounds, made here (16-bit mono at CODER_RATE): the bell, a hello, a call for
    you, an uh-oh, a shrug. b"" for a pose with no sound."""
    if name in CODER_SOUNDS:
        return CODER_SOUNDS[name]
    import numpy as np
    r = CODER_RATE

    def note(f, dur, decay, amp=1.0, glide=None, harmonics=((1, 1.0),), attack=0.004):
        """A tone that dies away (glide: the frequency it slides to)."""
        t = np.arange(int(dur * r)) / r
        if glide:                                   # an even slide, in pitch
            k = math.log(glide / f) / dur
            phase = 2 * math.pi * f * (np.expm1(k * t) / k)
        else:
            phase = 2 * math.pi * f * t
        env = np.exp(-t / decay) * np.minimum(1.0, t / attack)
        return amp * env * sum(a * np.sin(phase * h) for h, a in harmonics)

    def at(parts, total):
        out = np.zeros(int(total * r))
        for start, sig in parts:
            i = int(start * r)
            n = min(len(sig), len(out) - i)
            out[i:i + n] += sig[:n]
        return out

    if name == "done":                             # a desk bell: a few out-of-tune partials, ringing on
        f = 2093.0
        sig = at([(0, note(f, 1.8, 1.3, 0.5)), (0, note(f + 3.5, 1.8, 1.1, 0.3)),
                  (0, note(f * 2.32, 1.8, 0.42, 0.26)), (0, note(f * 4.25, 1.8, 0.16, 0.12))], 1.8)
        click = np.random.default_rng(7).standard_normal(int(0.004 * r)) * np.linspace(0.25, 0, int(0.004 * r))
        sig[:len(click)] += click
    elif name == "hello":                        # two notes going up: hello
        h = ((1, 1.0), (2, 0.25), (3, 0.08))
        sig = at([(0, note(1318.5, 0.9, 0.42, 0.4, harmonics=h)), (0.13, note(1975.5, 0.9, 0.45, 0.4, harmonics=h))], 1.1)
    elif name == "attention":                      # a soft "hey?"
        sig = at([(0, note(880, 0.2, 0.12, 0.45, attack=0.008)), (0.16, note(1318.5, 0.35, 0.16, 0.45, attack=0.008))], 0.55)
    elif name == "error":                          # uh-oh
        h = ((1, 1.0), (3, 0.18))
        sig = at([(0, note(784, 0.2, 0.16, 0.45, harmonics=h, attack=0.006)),
                  (0.17, note(523.3, 0.45, 0.2, 0.45, harmonics=h, attack=0.006))], 0.65)
    elif name == "shrug":                          # a shrug
        sig = note(520, 0.45, 0.5, 0.4, glide=300, harmonics=((1, 1.0), (2, 0.15)), attack=0.01)
    else:
        CODER_SOUNDS[name] = b""
        return b""
    fade = min(len(sig), int(0.05 * r))            # (no click at the end)
    sig[-fade:] *= np.linspace(1, 0, fade)
    pcm = (np.clip(sig, -1, 1) * 32000).astype("<i2").tobytes()
    CODER_SOUNDS[name] = pcm
    return pcm


def coder_wav(data):
    """The samples in a WAV an agent sent: (pcm, rate, channels). ValueError says what's wrong with it."""
    data = memoryview(data)
    if len(data) < 12 or bytes(data[:4]) != b"RIFF" or bytes(data[8:12]) != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, pcm = 12, None, None
    while pos + 8 <= len(data):
        cid = bytes(data[pos:pos + 4])
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if cid == b"data":                         # (a WAV made as it streams may say 0, or too much)
            pcm = data[pos + 8:] if size == 0 or pos + 8 + size > len(data) else data[pos + 8:pos + 8 + size]
            break
        if cid == b"fmt " and size >= 16 and pos + 8 + size <= len(data):
            tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", data[pos + 8:pos + 24])
            if tag == 0xFFFE and size >= 26:       # WAVE_FORMAT_EXTENSIBLE: the real one is further in
                tag = struct.unpack("<H", data[pos + 32:pos + 34])[0]
            fmt = (tag, ch, rate, bits)
        pos += 8 + size + (size & 1)
    if fmt is None:
        raise ValueError("not a WAV file")
    if pcm is None:
        raise ValueError("no audio data")
    tag, ch, rate, bits = fmt
    if tag != 1 or bits != 16 or ch not in (1, 2) or not 8000 <= rate <= 48000:
        raise ValueError("expected 16-bit PCM, mono or stereo, 8000 to 48000 Hz")
    n = len(pcm) - len(pcm) % (2 * ch)
    if n <= 0:
        raise ValueError("no audio data")
    return bytes(pcm[:n]), rate, ch


def coder_envelope(pcm, rate, ch, step=0.04):
    """How loud a clip is, every step seconds, 0 to 1 (its loud parts are 1): its mouth follows it."""
    import numpy as np
    win = max(1, int(rate * step)) * ch
    a = np.frombuffer(pcm, dtype="<i2")
    out = []
    for i in range(0, len(a), win * 256):          # a bit at a time: a long clip stays small in memory
        part = a[i:i + win * 256].astype(np.float32)
        n = len(part) // win * win
        if n:
            out.extend(np.sqrt((part[:n].reshape(-1, win) ** 2).mean(axis=1)).tolist())
        if len(part) > n:
            out.append(float(np.sqrt((part[n:] ** 2).mean())))
    if not out:
        return []
    loud = max(float(np.percentile(out, 95)), 300.0)
    return [min(1.0, v / loud) for v in out]


def co_span(secs):
    """4 min, 40 s, 1 h 12 min."""
    secs = max(0, int(secs))
    if secs < 60:
        return f"{secs} s"
    if secs < 3600:
        return f"{secs // 60} min"
    return f"{secs // 3600} h {secs // 60 % 60} min"


# prompts for your coding agent, typed on the Pi (A on the Bot at work)
CODER_CHANNEL = "pitato"   # what Claude Code calls coder_hooks.py --channel, which hands it your prompts
PROMPT_MAX = 2000          # characters in a prompt
PROMPT_WAIT = 20           # seconds your agent's request for prompts waits for one at most (then it asks again)
PROMPT_LISTEN = 45         # seconds since it last asked that it still counts as listening
PROMPT_ACK = 15            # seconds it has to say it got a prompt it was handed (or the next request gets it)
PROMPT_KEEP = 60           # seconds a prompt waits to be taken, then it's yours to send again


class AgentPrompts:
    """Prompts typed on the Pi for your coding agent, until it takes them. coder_hooks.py --channel (Claude
    Code runs it) asks for them: POST /coder/prompts, which waits a while for one. Each request says
    the last prompt it got: until then, one it was handed may not have reached it, and the next request
    gets it again. run tells this Pi's prompts from those before it restarted."""

    def __init__(self):
        self.cv = threading.Condition()
        self.queue = []                 # {"id", "text", "at", "out"}: waiting (out None), or handed out (out: when)
        self.run = secrets.token_hex(4)
        self.next_id = 1
        self.asked = -1e9               # when your agent last asked (time.monotonic())
        self.asking = 0                 # its requests waiting now
        self.on_taken = lambda prompt: None

    def listening(self):
        """Your agent is asking for prompts (or was, a moment ago)."""
        with self.cv:
            return self.asking > 0 or time.monotonic() - self.asked < PROMPT_LISTEN

    def put(self, text):
        with self.cv:
            prompt = {"id": self.next_id, "text": text, "at": time.monotonic(), "out": None}
            self.next_id += 1
            self.queue.append(prompt)
            self.cv.notify_all()
            return prompt["id"]

    def take(self, wait, got=0, run=""):
        """For your agent: the prompts waiting, at once or as soon as one comes (wait seconds at most),
        or none. got: the last one it got (from this run)."""
        if run != self.run:
            got = 0
        with self.cv:
            taken = [p for p in self.queue if p["id"] <= got]
            self.queue = [p for p in self.queue if p["id"] > got]
        for p in taken:
            self.on_taken(p)
        with self.cv:
            self.asking += 1
            end = time.monotonic() + max(0.0, min(float(wait), PROMPT_WAIT))
            try:
                while True:
                    now = time.monotonic()
                    for p in self.queue:            # handed out, but it never said it got it
                        if p["out"] is not None and now - p["out"] > PROMPT_ACK:
                            p["out"] = None
                    out = [p for p in self.queue if p["out"] is None]
                    if out or now >= end:
                        break
                    self.cv.wait(end - now)
                for p in out:
                    p["out"] = now
            finally:
                self.asking -= 1
                self.asked = time.monotonic()
        return {"ok": True, "run": self.run, "prompts": [{"id": p["id"], "text": p["text"]} for p in out]}

    def expire(self):
        """The prompts nobody took in time, back to you (oldest first)."""
        with self.cv:
            now = time.monotonic()
            old = [p for p in self.queue if now - p["at"] > PROMPT_KEEP
                   and (p["out"] is None or now - p["out"] > PROMPT_ACK)]
            self.queue = [p for p in self.queue if p not in old]
        return old


class Coder:
    """What the Bot is doing at work, from your coding agent's hooks: the pose, how long it has had it,
    and what comes next. It keeps time whether or not it's on screen, and makes its sounds itself
    (sound_ok says how loud and where, or None when it should keep quiet)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cv = threading.Condition(self.lock)
        now = time.monotonic()
        self.anim, self.since = "rest", now - CODER_HOLD   # (at rest already: the first word from an agent shows at once)
        self.prev = ("rest", now - 2, now - 1, False)   # the pose before (name, since, until, asleep): it moves on smoothly
        self.pending = None           # asked for while the pose before had its moment
        self.fresh = now              # the agent's last word about a busy pose
        self.asleep = False
        self.heard = 0.0              # when an agent last said something (time.time(); 0: not yet)
        self.work_from = None         # when this stretch of work began (time.time())
        self.done = None              # (when it was last done, how long it took)
        self.clip = None              # a clip being said: {"env", "step", "start"}
        self.seed = random.random()
        self.speaker = threading.Lock()     # one sound at a time
        self.sounds = []              # [(when, name)] still to make (time.monotonic())
        self.sound_ok = lambda: None  # -> (aplay's device, volume), or None to keep quiet
        self.on_change = lambda: None
        self.on_news = lambda name: None    # it's done, or it needs you
        self.news_q = []              # ...said by its own clock, for run() to pass on
        threading.Thread(target=self.run, daemon=True, name="coder").start()

    def changed(self):
        try:
            self.on_change()
        except Exception as ex:                      # (its clock keeps going, whatever happens)
            print(f"coder: {ex!r}", flush=True)

    @staticmethod
    def hold(name):
        """How long a pose has before the next one: a one-off gesture finishes first, and resting
        has no need to wait."""
        return 0.0 if name == "rest" else CODER_ONCE.get(name, CODER_HOLD)

    def begin(self, name, now, sound=True):
        """On to a pose (the lock is held)."""
        self.prev = (self.anim, self.since, now, self.asleep)
        self.anim, self.since, self.fresh = name, now, now
        if name not in ("rest", "sleep"):
            self.asleep = False
        wall = time.time()
        if name in ("typing", "reading", "thinking"):
            if self.work_from is None:
                self.work_from, self.done = wall, None
        elif name == "done":
            self.done = (wall, wall - self.work_from if self.work_from else 0.0)
            self.work_from = None
        elif name in ("hello", "wake", "sleep"):
            self.work_from = None
        if sound and name in CODER_SOUND_AT:
            self.sounds.append((now + CODER_SOUND_AT[name], name))
            self.sounds.sort()
        self.cv.notify()                               # (its clock has something new to keep time for)

    def step(self, now):
        """Moves on to whatever is due by now (the lock is held)."""
        for _ in range(6):
            a, t = self.anim, now - self.since
            if self.clip:
                return
            if self.pending and t >= self.hold(a):
                name, self.pending = self.pending, None
                self.begin(name, now)
            elif a in CODER_ONCE and t >= CODER_ONCE[a]:
                if a == "sleep":
                    self.asleep = True
                self.begin("rest", self.since + CODER_ONCE[a], sound=False)
            elif a in CODER_WAIT and t >= CODER_WAIT[a]:
                self.begin("rest", self.since + CODER_WAIT[a])
            elif a in CODER_BUSY and now - self.fresh >= CODER_STUCK:
                late = now - self.fresh > CODER_STUCK + 5      # (the Pi was busy, or asleep itself)
                self.begin("attention", self.fresh + CODER_STUCK, sound=not late)
                self.news_q.append("attention")
            elif a == "rest" and not self.asleep and t >= CODER_NAP:
                self.begin("sleep", self.since + CODER_NAP)
            else:
                return

    def due(self, now):
        """When step has something to do next (the lock is held)."""
        a, ds = self.anim, [now + 3600]
        if self.clip:
            return now + 3600                          # (say() moves on when the clip ends)
        if self.pending:
            ds.append(self.since + self.hold(a))
        if a in CODER_ONCE:
            ds.append(self.since + CODER_ONCE[a])
        if a in CODER_WAIT:
            ds.append(self.since + CODER_WAIT[a])
        if a in CODER_BUSY:
            ds.append(self.fresh + CODER_STUCK)
        if a == "rest" and not self.asleep:
            ds.append(self.since + CODER_NAP)
        if self.sounds:
            ds.append(self.sounds[0][0])
        return min(ds)

    def run(self):
        """Its clock: poses that have had their time move on, and sounds go out when they're due,
        on screen or not."""
        while True:
            with self.cv:
                now = time.monotonic()
                was = (self.anim, self.since, self.asleep)
                self.step(now)
                news, self.news_q = self.news_q, []
                sound = self.sounds.pop(0)[1] if self.sounds and self.sounds[0][0] <= now else None
                moved = (self.anim, self.since, self.asleep) != was
                if not moved and sound is None and not news:
                    self.cv.wait(max(0.01, self.due(now) - now))
                    continue
            if moved:
                self.changed()
            for name in news:
                self.news(name)
            if sound:
                threading.Thread(target=self.effect, args=(sound,), daemon=True, name="coder-sound").start()

    def news(self, name):
        try:
            self.on_news(name)
        except Exception as ex:
            print(f"coder: {ex!r}", flush=True)

    def ask(self, name, agent=True):
        """An agent (or you, with a button) asks for a pose. What it's doing now, which may still be
        the one before: each pose has at least a second, and a one-off gesture finishes first."""
        with self.cv:
            now = time.monotonic()
            self.step(now)
            if agent:
                self.heard = time.time()
            if self.clip:
                self.pending = name                    # (after the clip)
            elif self.asleep and name in ("rest", "sleep") and self.anim == "rest":
                self.pending = None                    # asleep already
            elif name == self.anim and (name in CODER_BUSY or name in CODER_WAIT):
                self.pending, self.fresh = None, now   # still at it (or still needs you: no second call)
            elif now - self.since >= self.hold(self.anim):
                self.pending = None
                self.begin(name, now)
            else:
                self.pending = name
            self.cv.notify()
            cur = self.anim
        self.changed()
        if agent and name in ("done", "attention"):
            self.news(name)
        return cur

    def current(self):
        with self.cv:
            self.step(time.monotonic())
            return self.anim

    def snapshot(self, now):
        """All the screen needs, at once."""
        with self.cv:
            self.step(now)
            energy = None
            if self.clip:
                c = self.clip
                i = int((now - c["start"]) / c["step"])
                energy = c["env"][i] if 0 <= i < len(c["env"]) else 0.0
            return {"anim": self.anim, "t": now - self.since, "asleep": self.asleep, "prev": self.prev,
                    "since": self.since, "energy": energy, "heard": self.heard, "work_from": self.work_from,
                    "done": self.done, "seed": self.seed, "clip": self.clip is not None}

    def pose(self, now, s=None):
        """Its pose now, moving smoothly on from the one before."""
        s = s or self.snapshot(now)
        p = coder_pose(s["anim"], s["t"], now, s["asleep"], s["energy"], s["seed"])
        if s["t"] < CODER_EASE:
            name, since, until, asleep = s["prev"]
            before = coder_pose(name, until - since, now, asleep, None, s["seed"])
            p = coder_blend(before, p, co_ease(s["t"] / CODER_EASE))
        return p

    # its sounds
    def effect(self, name):
        """One of its own sounds, when nothing else is using the speaker."""
        how = self.sound_ok()
        pcm = coder_sound(name) if how else b""
        if not pcm or not self.speaker.acquire(blocking=False):
            return
        try:
            self.aplay(pcm, CODER_RATE, 1, *how)
        finally:
            self.speaker.release()

    @staticmethod
    def aplay(pcm, rate, ch, device, volume):
        """Samples to the speaker (16-bit) at the media volume. True once they've all played."""
        if not shutil.which("aplay"):
            return False
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", str(ch), "-r", str(rate)]
        if device:
            cmd += ["-D", device]
        try:
            play = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False
        import numpy
        k = max(0, min(100, volume)) / 100.0
        try:
            for i in range(0, len(pcm), 16384):
                part = pcm[i:i + 16384]
                if k < 1:
                    part = (numpy.frombuffer(part, dtype="<i2").astype(numpy.float32) * k).astype("<i2").tobytes()
                play.stdin.write(part)
            play.stdin.close()
            play.wait(timeout=len(pcm) / (2 * ch * rate) + 10)
            return play.returncode == 0
        except (OSError, ValueError, subprocess.TimeoutExpired):
            try:
                play.kill()
            except OSError:
                pass
            return False

    def say(self, pcm, rate, ch, pose="talking"):
        """A clip an agent sent, said in a pose (its mouth following it when talking), then back to
        what it was busy with; whatever was asked for meanwhile comes after it. Clips take turns.
        Without a speaker to use (sound off, or something playing) it mouths it. How long it took
        (ms), once it's done."""
        secs = len(pcm) / (2 * ch * rate)
        env = coder_envelope(pcm, rate, ch)
        with self.speaker:
            how = self.sound_ok()
            with self.cv:
                now = time.monotonic()
                self.step(now)
                back = self.anim if self.anim in CODER_BUSY else "rest"
                self.begin(pose, now, sound=False)
                self.clip = {"env": env, "step": 0.04, "start": now}
                self.heard = time.time()
                self.cv.notify()
            self.changed()
            t0 = time.monotonic()
            if not (how and self.aplay(pcm, rate, ch, *how)):
                time.sleep(max(0.0, secs - (time.monotonic() - t0)))
            with self.cv:
                now = time.monotonic()
                self.clip = None
                nxt, self.pending = self.pending or back, None
                self.begin(nxt, now)
                self.cv.notify()
            self.changed()
        return int(secs * 1000)

    def talking(self):
        """A clip is being said."""
        return self.clip is not None
