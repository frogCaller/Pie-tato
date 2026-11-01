"""The bot's face: two big eyes and a little mouth, drawn as shapes (sharp at any size), that blink, glance about,
and show what it's doing (listening, thinking, talking) and how it feels (happy, sorry, curious, sleepy, cool). In
the colour you pick, on the background you pick, with eyelashes if you like (Settings > Bot).
face_state() says how it looks at a moment; draw_face() draws it; face_wait() says when it next changes, so the
screen is only drawn again when it does (a blink, a glance), not all the time."""
import math

from .theme import BG, co_mix, ROW

LOOKS = ("idle", "happy", "sad", "cool", "curious", "sleepy", "thinking", "listening", "talking", "alert")
MOODS = {   # the bot's moods (bot.py's friend_face) as looks
    "happy": "happy", "pleased": "idle", "cool": "cool", "curious": "curious", "sorry": "sad", "worried": "sad",
    "sleepy": "sleepy", "thinking": "thinking", "plain": "idle", "surprised": "alert"}
BLINK = 0.16               # seconds a blink takes
GLANCE = 0.28              # ...and a glance, from one place to the next
BUSY_FPS = 12              # frames a second while it's talking, thinking or listening (the rest: as it changes)
SLEEPY_FPS = 5             # ...and while it dozes (its eyes and its z's drift slowly)
STILL = ("thinking", "listening", "talking", "alert")   # (looks whose eyes don't glance about)
LISTEN_GAP = 0.05          # listening: its sound's arcs start this far (of its size) past the eye's edge
THINK_DOTS = 0.5           # thinking: its dots this far (of its size) above its middle, a gap above its eyes
LASH_WIDE = 0.032          # an eyelash: a short stroke this wide (of its size) where it leaves the eye...
LASH_TIP = 0.5             # ...narrowing to this much of that at its end, rounded off there
LASHES = ((38, 0.06), (60, 0.065), (82, 0.06))   # three on each eye's top outer corner: where (degrees round from
                           # straight up), and how long (of its size); each pointing a little further out than that

# Its colours (Settings > Bot > Face colour, Background): up and down, on just its face, go from one to the next
FACE_COLOURS = (("White", (236, 239, 243)), ("Sky", (128, 196, 255)), ("Aqua", (94, 224, 222)),
                ("Mint", (120, 230, 168)), ("Lime", (196, 236, 110)), ("Lemon", (255, 226, 102)),
                ("Peach", (255, 178, 128)), ("Coral", (255, 128, 112)), ("Pink", (255, 140, 196)),
                ("Lilac", (196, 164, 255)))
FACE_BACKS = (("Matching", None), ("Dark", None),   # Matching: a deep shade of its colour (white's: Dark); Dark: the
              ("Black", ((0, 0, 0), (22, 22, 24))),   # menus' own. The rest: (the screen behind it, its card)
              ("Navy", ((14, 24, 50), (26, 40, 74))), ("Plum", ((40, 18, 46), (60, 32, 68))),
              ("Forest", ((12, 36, 28), (24, 54, 44))), ("Wine", ((48, 14, 26), (70, 26, 42))))
FACE_TINT = (0.16, 0.2)    # Matching: this much of its colour in the screen's dark, and in its card's


def _hash(n):
    """A steady pseudo-random number in [0, 1) for each whole n: the same face at the same moment."""
    n = (int(n) * 2654435761 + 0x9E3779B9) & 0xFFFFFFFF
    n ^= n >> 15
    n = (n * 2246822519) & 0xFFFFFFFF
    n ^= n >> 13
    return (n & 0xFFFF) / 65536.0


def _blink_at(k):
    """When the blink in the k-th four seconds starts (and whether it's a double one)."""
    return k * 4.0 + 0.4 + _hash(k) * 2.8, _hash(k + 7919) < 0.18


def _openness(t, look):
    """How open the eyes are at t: 1 open, 0 shut (a blink every few seconds)."""
    if look == "sleepy":
        return 0.18 + 0.06 * math.sin(t * 1.3)
    k = math.floor(t / 4.0)
    for kk in (k - 1, k):
        start, double = _blink_at(kk)
        for s in ((start, start + BLINK + 0.12) if double else (start,)):
            if s <= t < s + BLINK:
                return abs(math.cos(math.pi * (t - s) / BLINK))
    return 1.0


GAZES = ((0, 0), (0, 0), (0, 0), (-1, 0), (1, 0), (-0.7, -0.6), (0.7, -0.6), (0, 0.5), (-1, 0.3), (1, 0.3))


def _gaze_at(k):
    """Where the eyes rest in the k-th three seconds."""
    return GAZES[int(_hash(k + 101) * len(GAZES))]


def _gaze(t, look):
    """Where the eyes look at t ((-1..1, -1..1): left to right, up to down), moving from one place to the next."""
    if look == "thinking":
        return 0.75, -0.75
    if look in STILL:
        return 0.0, 0.0
    k = math.floor(t / 3.0)
    here, was = _gaze_at(k), _gaze_at(k - 1)
    into = t - k * 3.0
    if into < GLANCE:
        e = into / GLANCE
        e = e * e * (3 - 2 * e)
        return was[0] + (here[0] - was[0]) * e, was[1] + (here[1] - was[1]) * e
    return here


def face_state(look, t):
    """How the face is at time t: (how open the eyes are, where they look (dx, dy), how open the mouth is,
    how much bigger the eyes are)."""
    look = look if look in LOOKS else "idle"
    opened = _openness(t, look)
    dx, dy = _gaze(t, look)
    mouth = 0.0
    if look == "talking":                              # (a beat to its words: never quite the same twice)
        mouth = max(0.0, 0.55 + 0.45 * math.sin(t * 13.0) * math.sin(t * 4.1 + 1.0))
    grow = 1.0
    if look == "listening":
        grow = 1.08 + 0.03 * math.sin(t * 5.0)
    elif look == "alert":
        grow = 1.14
    return opened, (dx, dy), mouth, grow


def face_wait(look, t):
    """Seconds until the face looks different from how it looks at t (for when to draw it next): a frame every
    twentieth of a second through a blink or a glance, none between them."""
    if look in ("talking", "thinking", "listening"):
        return 1.0 / BUSY_FPS
    if look == "sleepy":
        return 1.0 / SLEEPY_FPS
    k = math.floor(t / 4.0)
    soon = []
    for kk in (k - 1, k, k + 1):
        start, double = _blink_at(kk)
        end = start + BLINK + (BLINK + 0.12 if double else 0)
        if start <= t < end:
            return 1.0 / 20
        if start > t:
            soon.append(start - t)
    if look not in STILL:
        g = math.floor(t / 3.0)
        if t - g * 3.0 < GLANCE and _gaze_at(g) != _gaze_at(g - 1):
            return 1.0 / 20
        n = g + 1
        while _gaze_at(n) == _gaze_at(n - 1) and n < g + 8:   # (the next time they move)
            n += 1
        soon.append(n * 3.0 - t)
    return max(0.02, min(soon))


def _mix(a, b, k):
    return tuple(int(x + (y - x) * k) for x, y in zip(a, b))


def face_colours(colour, back):
    """(its face's colour, the screen behind it, its card's: the chat page's) for a face colour and a background,
    by their names (one that isn't: the first)."""
    face = dict(FACE_COLOURS).get(colour, FACE_COLOURS[0][1])
    fixed = dict(FACE_BACKS).get(back, FACE_BACKS[0][1]) if back in dict(FACE_BACKS) else None
    if fixed:
        return face, fixed[0], fixed[1]
    if back in (None, "", "Matching") and face != FACE_COLOURS[0][1]:
        return face, co_mix(BG, face, FACE_TINT[0]), co_mix(ROW, face, FACE_TINT[1])
    return face, BG, ROW


def _lash(d, x, y, ux, uy, length, wide, colour):
    """An eyelash: a short stroke from (x, y) out along (ux, uy), wide across where it leaves the eye, narrowing
    toward its end, and rounded off there (no wider than the stroke itself)."""
    px, py = -uy, ux                                   # (square to it)
    tip = wide * LASH_TIP
    ex, ey = x + ux * (length - tip / 2), y + uy * (length - tip / 2)   # (where the rounding begins)
    pts = [(x + px * wide / 2, y + py * wide / 2), (ex + px * tip / 2, ey + py * tip / 2)]
    a0 = math.atan2(py, px)
    for k in range(1, 8):                              # (round over its end: half a circle, its own width)
        a = a0 - math.pi * k / 8
        pts.append((ex + math.cos(a) * tip / 2, ey + math.sin(a) * tip / 2))
    pts += [(ex - px * tip / 2, ey - py * tip / 2), (x - px * wide / 2, y - py * wide / 2)]
    d.polygon(pts, fill=colour)


def _corner_lashes(d, box, r, side, size, colour, down=False):
    """Eyelashes on the top outer corner of box (x0, y0, x1, y1: an eye, or a lens), its corners r round, side -1 for
    the left eye, 1 the right: three short strokes standing out from its edge. down: on its bottom outer corner
    instead, pointing down (shut eyes', asleep)."""
    x0, y0, x1, y1 = box
    r = max(0.5, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    up = 1 if down else -1                             # (which way is up, for this corner)
    ccx, ccy = (x1 - r if side > 0 else x0 + r), (y1 - r if down else y0 + r)
    wide = max(1.0, size * LASH_WIDE)
    for at, long in LASHES:
        a, b = math.radians(at), math.radians(at + 6)
        bx, by = ccx + side * math.sin(a) * (r - wide * 0.3), ccy + up * math.cos(a) * (r - wide * 0.3)
        _lash(d, bx, by, side * math.sin(b), up * math.cos(b), size * long, wide, colour)


def _slant_lashes(d, ax, ay, bx, by, side, size, colour):
    """Eyelashes on the outer end of a sorry eye's slanted top (from (ax, ay), its inner end, to (bx, by), its outer
    one): standing out from it, the outermost a little further out."""
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy) or 1.0
    base = math.atan2(abs(dy) / n, abs(dx) / n)        # (square to it, up and outward: degrees out from straight up)
    wide = max(1.0, size * LASH_WIDE)
    for (at, long), t, turn in zip(LASHES, (0.55, 0.74, 0.93), (0, 14, 28)):
        b = base + math.radians(turn)
        _lash(d, ax + dx * t, ay + dy * t, side * math.sin(b), -math.cos(b), size * long, wide, colour)


def draw_face(d, cx, cy, size, look, t, colour, back, font=None, lashes=False):
    """The face, size across, its middle at cx, cy, in colour on back (what's behind it: its eyes' shapes are cut
    with it). font: for a sleepy face's z's. lashes: eyelashes on its eyes (on its glasses, when it wears them)."""
    look = look if look in LOOKS else "idle"
    opened, (gx, gy), mouth, grow = face_state(look, t)
    ew, eh = size * 0.25 * grow, size * 0.36 * grow                 # an eye
    gap = size * 0.46                                               # between their middles
    ox, oy = gx * size * 0.07, gy * size * 0.06                     # where they look
    ey = cy - size * 0.08 + oy
    soft = _mix(back, colour, 0.18)
    for side in (-1, 1):
        ex = cx + side * gap / 2 + ox
        w, h = ew, eh
        if look == "curious":                          # (one eyebrow up: one eye bigger)
            k = 1.15 if side > 0 else 0.86
            w, h = ew * k, eh * k
        hh = max(size * 0.035, h * opened)
        box = (ex - w / 2, ey - hh / 2, ex + w / 2, ey + hh / 2)
        r = min(w, hh) * 0.48
        if look == "cool":                             # (dark glasses: the eyes behind them)
            continue
        d.rounded_rectangle(box, radius=r, fill=colour)
        if look == "happy" and opened > 0.5:           # smiling eyes: their lower halves cut away in a curve
            cut = h * 0.62
            d.ellipse((ex - w * 0.75, ey + h * 0.5 - cut * 0.55, ex + w * 0.75, ey + h * 0.5 + cut * 1.1), fill=back)
        elif look == "sad" and opened > 0.5:           # their outer tops slanting down
            x_out = ex + side * w * 0.62
            d.polygon([(x_out, ey - h * 0.62), (ex - side * w * 0.62, ey - h * 0.62), (x_out, ey - h * 0.02)],
                      fill=back)
        elif look == "sleepy":
            pass
        elif opened > 0.6 and look not in ("happy",):  # a glint, top left of each eye
            gr = w * 0.13
            d.ellipse((ex - w * 0.22 - gr, ey - hh * 0.24 - gr, ex - w * 0.22 + gr, ey - hh * 0.24 + gr), fill=soft
                      if colour == back else _mix(colour, (255, 255, 255), 0.6))
        if lashes and look == "sad" and opened > 0.5:  # (along its slanted top)
            _slant_lashes(d, ex - side * w * 0.3, ey - h * 0.62 + h * 0.6 * 0.26, ex + side * w * 0.5,
                          ey - h * 0.62 + h * 0.6 * 0.9, side, size, colour)
        elif lashes:
            _corner_lashes(d, box, r, side, size, colour, down=look == "sleepy")
    if look == "cool":                                 # the glasses: a bar, two lenses, a shine
        lw, lh = size * 0.36, size * 0.26
        y0 = ey - lh / 2
        d.rounded_rectangle((cx - gap / 2 - lw / 2 + ox, y0, cx + gap / 2 + lw / 2 + ox, y0 + size * 0.05),
                            radius=size * 0.02, fill=colour)
        for side in (-1, 1):
            lx = cx + side * gap / 2 + ox
            d.rounded_rectangle((lx - lw / 2, y0, lx + lw / 2, y0 + lh), radius=size * 0.08, fill=colour)
            d.line((lx - lw * 0.28, y0 + lh * 0.3, lx - lw * 0.08, y0 + lh * 0.12), fill=back, width=max(1, round(
                size * 0.02)))
            if lashes:                                 # (over its glasses, at their outer corners)
                _corner_lashes(d, (lx - lw / 2, y0, lx + lw / 2, y0 + lh), size * 0.08, side, size, colour)
    # the mouth
    my, mw = cy + size * 0.27 + oy * 0.5, size * 0.17
    mx = cx + ox * 0.6
    line = max(1, round(size * 0.028))
    if look == "talking":
        mh = size * (0.03 + 0.11 * mouth)
        d.rounded_rectangle((mx - mw * 0.55, my - mh / 2, mx + mw * 0.55, my + mh / 2), radius=min(mh, mw) * 0.45,
                            fill=colour)
    elif look in ("happy",):
        d.chord((mx - mw, my - mw * 0.75, mx + mw, my + mw * 0.6), 10, 170, fill=colour)
    elif look == "sad":
        d.arc((mx - mw * 0.8, my, mx + mw * 0.8, my + mw * 1.1), 200, 340, fill=colour, width=line)
    elif look in ("curious", "alert"):
        r = size * (0.045 if look == "curious" else 0.06)
        d.ellipse((mx - r, my - r, mx + r, my + r), outline=colour, width=line)
    elif look == "sleepy":
        d.line((mx - mw * 0.4, my, mx + mw * 0.4, my), fill=colour, width=line)
    elif look == "thinking":
        d.line((mx - mw * 0.2, my + size * 0.01, mx + mw * 0.6, my - size * 0.02), fill=colour, width=line)
    elif look == "cool":
        d.arc((mx - mw * 0.5, my - mw * 0.8, mx + mw * 0.9, my + mw * 0.3), 30, 120, fill=colour, width=line)
    else:                                              # idle, listening: a little smile
        d.arc((mx - mw * 0.7, my - mw * 0.9, mx + mw * 0.7, my + mw * 0.35), 25, 155, fill=colour, width=line)
    # what goes with it
    if look == "thinking":                             # three dots, one after another, well clear of its eyes
        for k in range(3):
            on = int(t * 3) % 3 == k
            r = size * (0.032 if on else 0.024)
            x = cx + size * 0.36 + k * size * 0.1
            y = cy - size * THINK_DOTS
            d.ellipse((x - r, y - r, x + r, y + r), fill=colour if on else soft)
    elif look == "listening":                          # sound coming in, from one side (a little way off the eye)
        for k in range(3):
            phase = (t * 1.6 - k * 0.33) % 1.0
            r = size * (0.08 + 0.05 * k)
            x = cx + gap / 2 + ew / 2 + size * LISTEN_GAP
            d.arc((x - r, ey - r, x + r, ey + r), -40, 40, fill=_mix(back, colour, 1.0 - phase * 0.8),
                  width=line)
    elif look == "sleepy" and font is not None:        # z's, drifting up
        for k in range(2):
            p = (t * 0.35 + k * 0.5) % 1.0
            x = cx + size * (0.3 + 0.12 * p + 0.08 * k)
            y = cy - size * (0.3 + 0.35 * p)
            d.text((x, y), "z", font=font, fill=_mix(colour, back, p), anchor="mm")
    elif look == "alert":
        d.rounded_rectangle((cx - size * 0.022, cy - size * 0.62, cx + size * 0.022, cy - size * 0.44),
                            radius=size * 0.02, fill=colour)
        d.ellipse((cx - size * 0.024, cy - size * 0.41, cx + size * 0.024, cy - size * 0.36), fill=colour)
