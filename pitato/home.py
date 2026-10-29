"""The home screen's icons, and the background behind them."""
import math

from .theme import co_mix, FONT_BOLD


def wallpaper(name, size, picture=""):
    """The home screen's background: a picture (darkened so the icons read), or a soft
    gradient with a glow, worked out small and scaled up so it costs little."""
    from PIL import Image, ImageDraw, ImageFilter, ImageOps
    w, h = size
    if name == "Picture" and picture:
        try:
            im = ImageOps.fit(ImageOps.exif_transpose(Image.open(picture)).convert("RGB"), size,
                              Image.LANCZOS)
            return Image.blend(im, Image.new("RGB", size, (0, 0, 0)), 0.45)
        except Exception:
            name = "Midnight"
    looks = {   # top colour, bottom colour, glows: (x, y, radius, colour) as fractions of the screen
        "Midnight": ((19, 23, 31), (11, 14, 19), []),
        "Black": ((0, 0, 0), (0, 0, 0), []),
        "Dusk": ((52, 36, 86), (14, 14, 30), [(0.85, 0.05, 0.55, (150, 84, 120))]),
        "Ocean": ((8, 66, 100), (6, 18, 32), [(0.15, 0.0, 0.6, (40, 140, 170))]),
        "Forest": ((22, 72, 52), (8, 20, 16), [(0.8, 0.1, 0.5, (70, 130, 80))]),
        "Aurora": ((10, 16, 30), (8, 14, 22), [(0.2, 0.15, 0.45, (40, 170, 140)),
                                               (0.65, 0.05, 0.5, (100, 80, 200)),
                                               (0.95, 0.35, 0.35, (40, 110, 190))]),
    }
    top, bottom, glows = looks.get(name, looks["Midnight"])
    sw, sh = max(w // 4, 1), max(h // 4, 1)
    small = Image.new("RGB", (sw, sh))
    d = ImageDraw.Draw(small)
    for y in range(sh):
        t = y / max(sh - 1, 1)
        d.line((0, y, sw, y), fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    for gx, gy, gr, col in glows:
        glow = Image.new("L", (sw, sh), 0)
        r = gr * sw
        ImageDraw.Draw(glow).ellipse((gx * sw - r, gy * sh - r, gx * sw + r, gy * sh + r), fill=110)
        glow = glow.filter(ImageFilter.GaussianBlur(r / 2))
        small = Image.composite(Image.new("RGB", (sw, sh), col), small, glow)
    return small.resize(size, Image.BICUBIC)


# ---- the home screen: an icon for each tab ------------------------------------------
HOME_COLS = (4, 5, 6)     # icons across: whichever fills the rows best (4 first, like a phone)


def home_cols(n, rows=3):
    """Columns for n icons so the last row isn't left with gaps (in up to `rows` rows)."""
    def gaps(c):
        r = -(-n // c)
        return (r > rows, r * c - n)
    return min(HOME_COLS, key=gaps)
def home_layout(n, cols):
    """(row, column) of each icon on the home screen. A short last row sits in the middle, so
    there are no gaps at its end (its columns can be halves)."""
    rows = -(-n // cols)
    last = n - (rows - 1) * cols
    out = []
    for k in range(n):
        r, c = divmod(k, cols)
        if r == rows - 1 and last < cols:
            c += (cols - last) / 2
        out.append((r, c))
    return out


HOME_ICONS = {    # tab name -> (its colour: its tile's tint, a line about it)
    "Home": ((92, 128, 184), "Your TV remote, lights and Pi-hole"),
    "TV": ((70, 122, 204), "Plex, Jellyfin, cartoons, films, news, sports, streams"),
    "Music": ((186, 104, 160), "Your music in ~/Music"),
    "Radio": ((132, 108, 214), "Internet radio"),
    "Photos": ((66, 176, 164), "Pictures in ~/Pictures"),
    "Videos": ((196, 104, 92), "Your videos in ~/Videos"),
    "Weather": ((78, 142, 206), "Now, the next hours and the week"),
    "Games": ((92, 184, 112), "Snake, and your Game Boy to PlayStation games"),
    "Files": ((102, 128, 174), "Your files, and your other computers'"),
    "Camera": ((128, 135, 148), "Your cameras: watch, steer, take pictures"),
    "Bot": ((210, 138, 76), "Chat, or watch your coding agent work"),
    "Simulator": ((118, 125, 140), "Rock paper scissors, fractals and more"),
    "Finance": ((184, 142, 66), "Stocks and coins: prices and charts"),
    "System": ((128, 135, 148), "Temperature, WiFi, storage"),
    "Settings": ((134, 140, 152), "WiFi, Bluetooth, background, sound, controllers"),
}
HOME_LABELS = {}   # a name -> a shorter one, for a name that doesn't fit under its tile (none, now)
TILE_TOP, TILE_BOTTOM = (40, 45, 55), (23, 27, 34)   # a tile's dark glass, before its tint
GLYPH_TOP, GLYPH_BOTTOM = (238, 240, 244), (176, 182, 192)   # the glyphs: light grey, lit from above
AMBER = (238, 166, 72)


def mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


FIN_BARS = ((50, 150), (106, 118), (162, 86))           # Finance's glyph (on the 252 square): three bars
FIN_LINE = ((38, 164), (92, 110), (132, 136), (196, 66))  # rising to 206, and a line going up over them
FIN_GREEN = (96, 206, 130)


def fin_arrow(line=FIN_LINE):
    """The arrowhead at the end of Finance's line: a triangle, on the 252 square."""
    (x0, y0), (x1, y1) = line[-2], line[-1]
    a = math.atan2(y1 - y0, x1 - x0)
    tip = (x1 + math.cos(a) * 14, y1 + math.sin(a) * 14)
    bx, by = tip[0] - math.cos(a) * 40, tip[1] - math.sin(a) * 40
    nx, ny = math.cos(a + math.pi / 2) * 26, math.sin(a + math.pi / 2) * 26
    return [tip, (bx + nx, by + ny), (bx - nx, by - ny)]


def fin_glyph(bars, gap, line, P, B, k, bar_fill, gap_fill, line_fill):
    """Finance's glyph: the bars (drawn by bars), a gap round the line (by gap) so it stands clear of them, and
    the line with its arrow (by line). P and B place points and boxes on the 252 square; k is its scale."""
    for x0, y0 in FIN_BARS:
        bars.rounded_rectangle(B(x0, y0, x0 + 40, 206), radius=max(1, int(9 * k)), fill=bar_fill)
    gap.line(P(*FIN_LINE), fill=gap_fill, width=max(1, int(30 * k)), joint="curve")
    gap.polygon(P(*fin_arrow()), fill=gap_fill, outline=gap_fill, width=max(1, int(16 * k)))
    line.line(P(*FIN_LINE), fill=line_fill, width=max(1, int(14 * k)), joint="curve")
    line.polygon(P(*fin_arrow()), fill=line_fill)


def tile_tint(name):
    return HOME_ICONS.get(name, ((120, 128, 142), ""))[0]


def draw_icon(name, size=84, card=True, lit=False):
    """An app's tile: dark glass tinted with its colour, a thin edge, and its glyph in light grey (a few parts in
    colour: a lit window, the sun, the bot's eyes), drawn three times bigger and scaled down so the edges come out
    smooth. lit: picked (brighter, a bright edge). (card: always, now; the web page's are the same.)"""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    import math
    S = size * 3
    tint = tile_tint(name)
    k = S * 0.74 / 252                               # the glyphs are laid out on a 252 square, in the middle
    o = S * 0.13

    def P(*pts):
        return [(o + x * k, o + y * k) for x, y in pts]

    def B(x0, y0, x1, y1):
        return (o + x0 * k, o + y0 * k, o + x1 * k, o + y1 * k)

    def R(r):
        return max(1, int(r * k))

    mask = Image.new("L", (S, S), 0)                 # the grey glyph: 255 where it is, holes cut back to 0
    under = Image.new("RGBA", (S, S), (0, 0, 0, 0))  # colour behind it (the sun behind the cloud)
    over = Image.new("RGBA", (S, S), (0, 0, 0, 0))   # colour on it
    d, du, do = ImageDraw.Draw(mask), ImageDraw.Draw(under), ImageDraw.Draw(over)

    def ring(draw, cx, cy, r, fill):
        draw.ellipse(B(cx - r, cy - r, cx + r, cy + r), fill=fill)

    if name == "Home":                             # a house, a light on
        d.polygon(P((24, 124), (126, 36), (228, 124)), fill=255)
        d.rounded_rectangle(B(56, 112, 196, 210), radius=R(10), fill=255)
        do.rounded_rectangle(B(104, 138, 148, 180), radius=R(6), fill=AMBER)
    elif name == "TV":
        for tip in ((90, 34), (162, 34)):
            d.line(P((126, 74), tip), fill=255, width=R(9))
        d.rounded_rectangle(B(30, 70, 222, 186), radius=R(20), fill=255)
        d.rounded_rectangle(B(48, 88, 204, 168), radius=R(10), fill=0)
        d.rectangle(B(118, 184, 134, 200), fill=255)
        d.rounded_rectangle(B(84, 196, 168, 210), radius=R(6), fill=255)
    elif name == "Music":
        d.rectangle(B(104, 68, 118, 168), fill=255)
        d.rectangle(B(180, 52, 194, 152), fill=255)
        d.polygon(P((104, 68), (194, 52), (194, 80), (104, 96)), fill=255)
        d.ellipse(B(62, 146, 118, 188), fill=255)
        d.ellipse(B(138, 130, 194, 172), fill=255)
    elif name == "Radio":                          # a mast, sending
        c = (126, 92)
        for r in (40, 66):
            box = B(c[0] - r, c[1] - r, c[0] + r, c[1] + r)
            d.arc(box, 145, 215, fill=255, width=R(11))
            d.arc(box, -35, 35, fill=255, width=R(11))

        def leg(y, side):
            return (126 + side * 32 * (y - 100) / 112, y)
        d.polygon(P(leg(100, -1), leg(212, -1), leg(212, 1), leg(100, 1)), fill=255)
        ring(d, 126, 92, 15, 255)
    elif name == "Photos":                         # a picture: mountains and the sun, cut out of it
        d.rounded_rectangle(B(28, 50, 224, 202), radius=R(18), fill=255)
        d.polygon(P((44, 186), (100, 112), (140, 160), (166, 132), (208, 186)), fill=0)
        ring(d, 176, 88, 16, 0)
    elif name == "Videos":                         # a clapperboard
        d.rounded_rectangle(B(40, 118, 212, 206), radius=R(12), fill=255)
        d.polygon(P((36, 82), (194, 50), (202, 86), (44, 116)), fill=255)
        for x in (58, 102, 146):                    # the stripes on its arm
            y = 80 - (x - 36) * 0.2
            d.polygon(P((x, y), (x + 22, y - 4), (x + 30, y + 30), (x + 8, y + 34)), fill=0)
        for x in (52, 96, 140, 184):                # ...and along its top
            d.polygon(P((x, 118), (x + 22, 118), (x + 8, 142), (x - 14, 142)), fill=0)
        d.rectangle(B(40, 140, 212, 146), fill=0)
    elif name == "Weather":                        # the sun behind a cloud
        ring(du, 166, 92, 46, (246, 190, 64))
        for x0, y0, x1, y1 in ((40, 122, 114, 196), (78, 86, 172, 180), (130, 118, 210, 198)):
            d.ellipse(B(x0, y0, x1, y1), fill=255)
        d.rounded_rectangle(B(60, 148, 194, 198), radius=R(25), fill=255)
    elif name == "Games":                          # a game controller
        d.rounded_rectangle(B(34, 86, 218, 162), radius=R(38), fill=255)
        for x0 in (38, 144):                         # its grips
            d.ellipse(B(x0, 102, x0 + 70, 196), fill=255)
        d.rounded_rectangle(B(78, 104, 96, 158), radius=R(4), fill=0)    # the d-pad
        d.rounded_rectangle(B(60, 122, 114, 140), radius=R(4), fill=0)
        for x, y in ((172, 110), (194, 131), (150, 131), (172, 152)):
            ring(d, x, y, 10, 0)
    elif name == "Files":                          # a folder
        du.rounded_rectangle(B(36, 56, 116, 98), radius=R(12), fill=(150, 157, 168))
        du.rounded_rectangle(B(36, 74, 216, 196), radius=R(14), fill=(150, 157, 168))
        d.rounded_rectangle(B(36, 98, 216, 204), radius=R(14), fill=255)
    elif name == "Camera":
        d.rounded_rectangle(B(86, 52, 166, 94), radius=R(12), fill=255)
        d.rounded_rectangle(B(30, 76, 222, 204), radius=R(26), fill=255)
        ring(d, 126, 142, 50, 0)
        ring(d, 126, 142, 34, 255)
        ring(d, 126, 142, 16, 0)
        d.rounded_rectangle(B(180, 94, 204, 110), radius=R(5), fill=0)
    elif name == "Bot":                            # its little head, antenna and all
        d.line(P((126, 72), (126, 44)), fill=255, width=R(9))
        ring(d, 126, 36, 13, 255)
        for x0 in (22, 212):                        # its ears
            d.rounded_rectangle(B(x0, 112, x0 + 18, 156), radius=R(7), fill=255)
        d.rounded_rectangle(B(36, 68, 216, 200), radius=R(42), fill=255)
        d.rounded_rectangle(B(56, 88, 196, 180), radius=R(28), fill=0)
        for x in (98, 154):
            do.rounded_rectangle(B(x - 14, 112, x + 14, 156), radius=R(12), fill=AMBER)
    elif name == "Simulator":                      # three orbits round a sun, a body on each
        def on(t, tilt, rx=100, ry=36):
            x, y = math.cos(t) * rx, math.sin(t) * ry
            return (126 + x * math.cos(tilt) - y * math.sin(tilt), 126 + x * math.sin(tilt) + y * math.cos(tilt))
        tilts = [math.radians(a) for a in (-30, 30, 90)]
        for tilt in tilts:
            d.line(P(*[on(t / 72 * 2 * math.pi, tilt) for t in range(73)]), fill=255, width=R(6), joint="curve")
        ring(do, 126, 126, 18, (246, 180, 64))
        for (t, tilt), body in zip(((0.0, tilts[0]), (math.pi, tilts[1]), (-math.pi / 2, tilts[2])),
                                   ((236, 98, 98), (96, 206, 130), (98, 142, 240))):
            x, y = on(t, tilt)
            ring(do, x, y, 13, body)
    elif name == "Finance":                        # bars rising, and a line going up over them, in green
        fin_glyph(d, d, do, P, B, k, 255, 0, FIN_GREEN + (255,))
    elif name == "System":                         # a chip
        d.rounded_rectangle(B(70, 70, 182, 182), radius=R(14), fill=255)
        d.rounded_rectangle(B(96, 96, 156, 156), radius=R(8), fill=0)
        for t in range(4):
            off = 88 + t * 25
            for a, b_ in (((off, 42), (off, 70)), ((off, 182), (off, 210)),
                          ((42, off), (70, off)), ((182, off), (210, off))):
                d.line(P(a, b_), fill=255, width=R(10))
    elif name == "Settings":                       # a gear
        pts = []
        for t in range(8):
            a = math.radians(t * 45)
            for r, da in ((66, -17), (92, -9), (92, 9), (66, 17)):
                pts.append((126 + r * math.cos(a + math.radians(da)), 126 + r * math.sin(a + math.radians(da))))
        d.polygon(P(*pts), fill=255)
        ring(d, 126, 126, 30, 0)
    else:                                           # a tab added by hand: its first letter
        try:
            font = ImageFont.truetype(FONT_BOLD, int(150 * k))
        except OSError:
            font = ImageFont.load_default()
        d.text((S / 2, S / 2), (name[:1] or "?").upper(), font=font, fill=255, anchor="mm")

    # the tile: dark glass with the app's tint, lighter at the top, a thin edge
    shape = Image.new("L", (S, S), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.23), fill=255)
    depth = 0.12 if lit else 0.0
    grad = Image.linear_gradient("L").resize((S, S))
    tile = Image.composite(Image.new("RGBA", (S, S), mix(TILE_BOTTOM, tint, 0.17 + depth) + (255,)),
                           Image.new("RGBA", (S, S), mix(TILE_TOP, tint, 0.30 + depth) + (255,)), grad)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(tile, (0, 0), shape)
    sheen = Image.new("RGBA", (S, S), (255, 255, 255, 0))       # glass: a little light along the top
    sheen.putalpha(grad.transpose(Image.FLIP_TOP_BOTTOM).point(lambda v: max(0, v - 150) // 6))
    out.alpha_composite(Image.composite(sheen, Image.new("RGBA", (S, S), (0, 0, 0, 0)), shape))
    edge = mix(tint, (255, 246, 200), 0.5) if lit else mix((66, 72, 84), tint, 0.5)
    ImageDraw.Draw(out).rounded_rectangle((1, 1, S - 2, S - 2), radius=int(S * 0.23), outline=edge + (255,),
                                          width=6 if lit else 3)

    # the glyph: a soft shadow under it, the colour behind, the grey (lit from above), the colour on it
    solid = Image.composite(Image.new("L", (S, S), 255), mask, under.getchannel("A"))
    solid = Image.composite(Image.new("L", (S, S), 255), solid, over.getchannel("A"))
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(solid.point(lambda v: v * 120 // 255).filter(ImageFilter.GaussianBlur(S / 60)))
    out.alpha_composite(shadow, (0, int(S / 60)))
    out.alpha_composite(under)
    grey = Image.composite(Image.new("RGBA", (S, S), GLYPH_BOTTOM + (255,)),
                           Image.new("RGBA", (S, S), GLYPH_TOP + (255,)), grad)
    grey.putalpha(mask)
    out.alpha_composite(grey)
    out.alpha_composite(over)
    out.putalpha(Image.composite(out.getchannel("A"), Image.new("L", (S, S), 0), shape))
    return out.resize((size, size), Image.LANCZOS)


# ---- Cards: coloured glyphs on dark cards --------------------------------------------------------------------
GLYPH_COLOURS = {    # an app's glyph's own colour
    "Home": (63, 116, 222), "TV": (58, 128, 234), "Music": (238, 72, 138), "Radio": (132, 88, 230),
    "Photos": (52, 196, 170), "Videos": (222, 52, 52), "Weather": (250, 204, 40), "Games": (74, 196, 90),
    "Files": (64, 140, 236), "Camera": (104, 112, 126), "Bot": (59, 130, 246), "Simulator": (64, 190, 100),
    "Finance": (247, 147, 26), "System": (148, 156, 170), "Settings": (34, 168, 226),
}
CARD = (26, 30, 37)          # the cards the glyphs sit on (and the dark parts of the glyphs themselves)
CARD_LINE = (44, 50, 61)     # ...their edge


def draw_glyph(name, size=52):
    """Cards's icon for an app: a glyph in its own colours (its dark parts the colour of the card it sits on),
    drawn three times bigger and scaled down so the edges come out smooth."""
    from PIL import Image, ImageDraw, ImageFont
    import math
    S = size * 3
    k = S / 252                                     # the glyphs are laid out on a 252 square
    colour = GLYPH_COLOURS.get(name, (200, 206, 214))
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    dark = CARD

    def P(*pts):
        return [(x * k, y * k) for x, y in pts]

    def B(x0, y0, x1, y1):
        return (x0 * k, y0 * k, x1 * k, y1 * k)

    def R(r):
        return int(r * k)

    def ring(cx, cy, r, fill):
        d.ellipse(B(cx - r, cy - r, cx + r, cy + r), fill=fill)

    if name == "Home":                             # a house, a light on
        d.polygon(P((24, 124), (126, 36), (228, 124)), fill=colour)
        d.rounded_rectangle(B(56, 112, 196, 210), radius=R(10), fill=colour)
        d.rounded_rectangle(B(78, 132, 116, 170), radius=R(6), fill=(246, 196, 60))
        d.rounded_rectangle(B(138, 146, 174, 214), radius=R(6), fill=dark)
    elif name == "TV":
        for tip in ((90, 36), (162, 36)):
            d.line(P((126, 74), tip), fill=colour, width=R(9))
        d.rounded_rectangle(B(36, 70, 216, 182), radius=R(18), fill=colour)
        d.rounded_rectangle(B(52, 86, 178, 166), radius=R(8), fill=dark)
        for y in (106, 126, 146):
            ring(197, y, 5, dark)
        d.rectangle(B(118, 180, 134, 198), fill=colour)
        d.rounded_rectangle(B(86, 194, 166, 208), radius=R(6), fill=colour)
    elif name == "Music":
        d.rectangle(B(104, 68, 118, 168), fill=colour)
        d.rectangle(B(180, 52, 194, 152), fill=colour)
        d.polygon(P((104, 68), (194, 52), (194, 80), (104, 96)), fill=colour)
        d.ellipse(B(62, 146, 118, 188), fill=colour)
        d.ellipse(B(138, 130, 194, 172), fill=colour)
    elif name == "Radio":                          # a mast, sending
        c = (126, 92)
        for r in (40, 66):
            box = B(c[0] - r, c[1] - r, c[0] + r, c[1] + r)
            d.arc(box, 145, 215, fill=colour, width=R(11))
            d.arc(box, -35, 35, fill=colour, width=R(11))

        def leg(y, side):
            return (126 + side * 32 * (y - 100) / 112, y)
        for side in (-1, 1):
            d.line(P(leg(100, side), leg(212, side)), fill=colour, width=R(10))
        for y0, y1 in ((134, 172), (172, 210)):
            d.line(P(leg(y0, -1), leg(y1, 1)), fill=colour, width=R(7))
            d.line(P(leg(y0, 1), leg(y1, -1)), fill=colour, width=R(7))
        ring(126, 92, 15, colour)
    elif name == "Photos":                         # mountains, the sun
        sun = (246, 186, 48)
        for t in range(8):
            a = math.radians(t * 45)
            d.line(P((176 + 30 * math.cos(a), 66 + 30 * math.sin(a)), (176 + 42 * math.cos(a), 66 + 42 * math.sin(a))),
                   fill=sun, width=R(7))
        ring(176, 66, 20, sun)
        d.polygon(P((26, 204), (102, 92), (180, 204)), fill=colour)
        d.polygon(P((94, 204), (160, 120), (228, 204)), fill=(24, 140, 122))
    elif name == "Videos":                         # a clapperboard
        d.rounded_rectangle(B(42, 112, 210, 204), radius=R(12), fill=colour)
        d.polygon(P((38, 80), (196, 50), (203, 84), (45, 114)), fill=colour)
        for x in (60, 104, 148):                    # the stripes on its arm
            y = 78 - (x - 38) * 0.19
            d.polygon(P((x, y), (x + 22, y - 4), (x + 28, y + 30), (x + 6, y + 34)), fill=dark)
        d.rectangle(B(42, 124, 210, 130), fill=dark)
    elif name == "Weather":                        # the sun behind a cloud
        ring(164, 92, 46, (245, 150, 22))
        for x0, y0, x1, y1 in ((44, 120, 116, 192), (82, 86, 170, 174), (132, 120, 206, 192)):
            d.ellipse(B(x0, y0, x1, y1), fill=colour)
        d.rounded_rectangle(B(62, 146, 192, 194), radius=R(24), fill=colour)
    elif name == "Games":                          # a game controller
        d.rounded_rectangle(B(34, 88, 218, 162), radius=R(37), fill=colour)
        for x0 in (40, 142):                         # its grips
            d.ellipse(B(x0, 104, x0 + 70, 194), fill=colour)
        d.rounded_rectangle(B(78, 104, 96, 158), radius=R(4), fill=dark)    # the d-pad
        d.rounded_rectangle(B(60, 122, 114, 140), radius=R(4), fill=dark)
        for x, y in ((170, 112), (192, 132), (148, 132), (170, 152)):
            ring(x, y, 10, dark)
    elif name == "Files":                          # a folder
        back = (40, 104, 210)
        d.rounded_rectangle(B(38, 62, 112, 96), radius=R(10), fill=back)
        d.rounded_rectangle(B(38, 78, 214, 192), radius=R(12), fill=back)
        d.rounded_rectangle(B(38, 100, 214, 200), radius=R(14), fill=colour)
    elif name == "Camera":
        d.rounded_rectangle(B(88, 58, 164, 94), radius=R(10), fill=colour)
        d.rounded_rectangle(B(34, 80, 218, 200), radius=R(24), fill=colour)
        ring(126, 140, 50, dark)
        ring(126, 140, 34, (37, 99, 235))
        ring(112, 126, 9, (147, 197, 253))
        d.rounded_rectangle(B(178, 96, 202, 112), radius=R(5), fill=dark)
    elif name == "Bot":                            # its little head, antenna and all
        d.line(P((126, 72), (126, 46)), fill=colour, width=R(9))
        ring(126, 38, 12, (147, 197, 253))
        for x0 in (24, 210):                        # its ears
            d.rounded_rectangle(B(x0, 112, x0 + 18, 156), radius=R(7), fill=colour)
        d.rounded_rectangle(B(38, 70, 214, 198), radius=R(40), fill=colour)
        d.rounded_rectangle(B(58, 90, 194, 178), radius=R(26), fill=dark)
        for x in (98, 154):
            d.rounded_rectangle(B(x - 14, 112, x + 14, 156), radius=R(12), fill=(147, 197, 253))
    elif name == "Simulator":                      # three orbits round a sun, a body on each
        def on(t, tilt, rx=98, ry=36):
            x, y = math.cos(t) * rx, math.sin(t) * ry
            return (126 + x * math.cos(tilt) - y * math.sin(tilt), 126 + x * math.sin(tilt) + y * math.cos(tilt))
        tilts = [math.radians(a) for a in (-30, 30, 90)]
        for tilt in tilts:
            d.line(P(*[on(t / 72 * 2 * math.pi, tilt) for t in range(73)]), fill=colour, width=R(6), joint="curve")
        ring(126, 126, 18, (250, 204, 21))
        for (t, tilt), body in zip(((0.0, tilts[0]), (math.pi, tilts[1]), (-math.pi / 2, tilts[2])),
                                   ((249, 115, 22), (59, 130, 246), (167, 112, 246))):
            x, y = on(t, tilt)
            ring(x, y, 13, body)
    elif name == "Finance":                        # bars rising, and a line going up over them
        fin_glyph(d, d, d, P, B, k, colour, dark, colour)
    elif name == "System":                         # a chip
        d.rounded_rectangle(B(74, 74, 178, 178), radius=R(14), fill=colour)
        d.rounded_rectangle(B(98, 98, 154, 154), radius=R(8), fill=dark)
        for t in range(4):
            off = 90 + t * 24
            for a, b_ in (((off, 46), (off, 74)), ((off, 178), (off, 206)),
                          ((46, off), (74, off)), ((178, off), (206, off))):
                d.line(P(a, b_), fill=colour, width=R(10))
    elif name == "Settings":                       # a gear
        pts = []
        for t in range(8):
            a = math.radians(t * 45)
            for r, da in ((64, -17), (88, -9), (88, 9), (64, 17)):
                pts.append((126 + r * math.cos(a + math.radians(da)), 126 + r * math.sin(a + math.radians(da))))
        d.polygon(P(*pts), fill=colour)
        ring(126, 126, 28, dark)
    else:                                           # a tab added by hand: its first letter
        try:
            font = ImageFont.truetype(FONT_BOLD, int(120 * k))
        except OSError:
            font = ImageFont.load_default()
        d.text((S / 2, S / 2), (name[:1] or "?").upper(), font=font, fill=colour, anchor="mm")
    return im.resize((size, size), Image.LANCZOS)


# ---- Bright: bright tiles, white glyphs ----------------------------------------------------------------------
BRIGHT_TILES = {    # an app's tile's colour
    "Home": (36, 54, 96), "TV": (62, 112, 204), "Music": (200, 82, 118), "Radio": (126, 96, 200),
    "Photos": (38, 146, 136), "Videos": (196, 84, 72), "Weather": (60, 150, 212), "Games": (58, 152, 96),
    "Files": (76, 114, 154), "Camera": (64, 72, 86), "Bot": (214, 132, 56), "Simulator": (30, 38, 46),
    "Finance": (8, 10, 10), "System": (88, 96, 110), "Settings": (112, 120, 134),
}


def draw_bright_icon(name, size=72):
    """The Bright style's icon for an app: a bright rounded tile with a simple white glyph, drawn three times
    bigger and scaled down so the edges come out smooth."""
    from PIL import Image, ImageDraw, ImageFont
    import math
    S = size * 3
    k = S / 252                                     # the glyphs are laid out on a 252 square
    colour = BRIGHT_TILES.get(name, (70, 80, 96))
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    dark = sum(colour) < 120
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(66 * k), fill=colour,
                        outline=(52, 58, 68) if dark else None, width=int(4 * k))
    white = (246, 248, 250)

    def P(*pts):
        return [(x * k, y * k) for x, y in pts]

    def B(x0, y0, x1, y1):
        return (x0 * k, y0 * k, x1 * k, y1 * k)

    if name == "Home":                             # a house, a light on
        d.polygon(P((30, 124), (126, 42), (222, 124)), fill=white)
        d.rounded_rectangle(B(60, 110, 192, 206), radius=int(10 * k), fill=white)
        d.rounded_rectangle(B(80, 128, 118, 166), radius=int(6 * k), fill=(255, 211, 94))
        d.rounded_rectangle(B(138, 142, 172, 206), radius=int(6 * k), fill=colour)
    elif name == "TV":
        for tip in ((96, 42), (156, 42)):
            d.line(P((126, 76), tip), fill=white, width=int(10 * k))
            d.ellipse(B(tip[0] - 7, tip[1] - 7, tip[0] + 7, tip[1] + 7), fill=white)
        d.rounded_rectangle(B(44, 74, 208, 178), radius=int(20 * k), fill=white)
        d.rounded_rectangle(B(60, 90, 192, 162), radius=int(8 * k), fill=colour)
        d.rectangle(B(118, 176, 134, 194), fill=white)
        d.rounded_rectangle(B(86, 190, 166, 204), radius=int(7 * k), fill=white)
    elif name == "Music":
        d.rectangle(B(104, 68, 118, 168), fill=white)
        d.rectangle(B(180, 52, 194, 152), fill=white)
        d.polygon(P((104, 68), (194, 52), (194, 80), (104, 96)), fill=white)
        d.ellipse(B(62, 146, 118, 188), fill=white)
        d.ellipse(B(138, 130, 194, 172), fill=white)
    elif name == "Radio":
        c = (126, 112)
        for r in (46, 78):
            box = B(c[0] - r, c[1] - r, c[0] + r, c[1] + r)
            d.arc(box, 140, 220, fill=white, width=int(13 * k))
            d.arc(box, -40, 40, fill=white, width=int(13 * k))
        d.polygon(P((126, 118), (98, 208), (154, 208)), fill=white)
        d.ellipse(B(108, 94, 144, 130), fill=white)
    elif name == "Photos":
        d.rounded_rectangle(B(40, 62, 212, 192), radius=int(20 * k), fill=white)
        d.polygon(P((54, 180), (106, 112), (140, 150), (168, 122), (200, 180)), fill=colour)
        d.ellipse(B(150, 78, 182, 110), fill=colour)
    elif name == "Videos":                          # a clapperboard
        d.rounded_rectangle(B(44, 104, 208, 198), radius=int(14 * k), fill=white)
        d.polygon(P((40, 74), (196, 46), (202, 78), (46, 106)), fill=white)
        for x in (62, 104, 146):                    # the stripes on the arm and the board
            d.polygon(P((x, 70 - (x - 40) * 0.18), (x + 20, 66 - (x - 40) * 0.18),
                        (x + 26, 98 - (x - 40) * 0.18), (x + 6, 102 - (x - 40) * 0.18)), fill=colour)
            d.polygon(P((x, 104), (x + 22, 104), (x + 8, 126), (x - 14, 126)), fill=colour)
        d.rectangle(B(44, 126, 208, 130), fill=colour)
    elif name == "Finance":                        # white bars rising, and a green line going up over them
        fin_glyph(d, d, d, P, B, k, white, colour, (74, 222, 128))
    elif name == "Files":
        d.polygon(P((42, 66), (104, 66), (124, 90), (42, 90)), fill=white)
        d.rounded_rectangle(B(42, 84, 210, 192), radius=int(16 * k), fill=white)
        d.rectangle(B(42, 102, 210, 108), fill=colour)
    elif name == "Camera":
        d.rounded_rectangle(B(92, 60, 160, 92), radius=int(10 * k), fill=white)
        d.rounded_rectangle(B(38, 82, 214, 194), radius=int(24 * k), fill=white)
        d.ellipse(B(82, 96, 170, 184), fill=colour)
        d.ellipse(B(102, 116, 150, 164), fill=white)
        d.ellipse(B(182, 100, 198, 116), fill=colour)
    elif name == "System":                         # a chip
        d.rounded_rectangle(B(74, 74, 178, 178), radius=int(14 * k), fill=white)
        d.rounded_rectangle(B(98, 98, 154, 154), radius=int(8 * k), fill=colour)
        for t in range(4):
            off = 90 + t * 24
            for a, b_ in (((off, 46), (off, 74)), ((off, 178), (off, 206)),
                          ((46, off), (74, off)), ((178, off), (206, off))):
                d.line(P(a, b_), fill=white, width=int(10 * k))
    elif name == "Settings":                       # a gear
        pts = []
        for t in range(8):
            a = math.radians(t * 45)
            for r, da in ((64, -17), (88, -9), (88, 9), (64, 17)):
                pts.append((126 + r * math.cos(a + math.radians(da)), 126 + r * math.sin(a + math.radians(da))))
        d.polygon(P(*pts), fill=white)
        d.ellipse(B(98, 98, 154, 154), fill=colour)
    elif name == "Weather":                        # sun behind a cloud
        d.ellipse(B(118, 52, 194, 128), fill=(255, 214, 90))
        for x0, y0, x1, y1 in ((52, 116, 120, 184), (88, 88, 168, 168), (136, 118, 200, 182)):
            d.ellipse(B(x0, y0, x1, y1), fill=white)
        d.rounded_rectangle(B(70, 140, 186, 184), radius=int(22 * k), fill=white)
    elif name == "Bot":                            # its little head, antenna and all
        d.line(P((126, 70), (126, 48)), fill=white, width=int(9 * k))
        d.ellipse(B(114, 30, 138, 54), fill=white)
        d.rounded_rectangle(B(40, 70, 212, 196), radius=int(40 * k), fill=white)
        d.rounded_rectangle(B(60, 88, 192, 178), radius=int(26 * k), fill=(30, 34, 42))
        for x in (98, 154):
            d.rounded_rectangle(B(x - 14, 112, x + 14, 154), radius=int(12 * k), fill=colour)
    elif name == "Simulator":                      # a sun, an orbit and three bodies going round it
        tilt = math.radians(-24)

        def on_orbit(t, rx=88, ry=46):
            x, y = math.cos(t) * rx, math.sin(t) * ry
            return (126 + x * math.cos(tilt) - y * math.sin(tilt), 126 + x * math.sin(tilt) + y * math.cos(tilt))
        glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        g.line(P(*[on_orbit(t / 60 * 2 * math.pi) for t in range(61)]), fill=(255, 255, 255, 46),
               width=int(4 * k), joint="curve")
        for r, a in ((34, 30), (26, 60), (20, 110)):
            g.ellipse(B(126 - r, 126 - r, 126 + r, 126 + r), fill=(255, 200, 96, a))
        im.alpha_composite(glow)
        d.ellipse(B(110, 110, 142, 142), fill=(255, 214, 120))
        for t0, body in ((0.35, (226, 123, 140)), (2.45, (127, 166, 222)), (4.4, (150, 236, 196))):
            for j in range(10, 0, -1):                # a tail, fading behind it
                t = t0 - j * 0.07
                x, y = on_orbit(t)
                r = 3 + 6 * (1 - j / 10)
                d.ellipse(B(x - r, y - r, x + r, y + r), fill=co_mix((30, 38, 46), body, 1 - j / 11))
            x, y = on_orbit(t0)
            d.ellipse(B(x - 13, y - 13, x + 13, y + 13), fill=body)
    elif name == "Games":                          # a game controller
        d.rounded_rectangle(B(34, 88, 218, 162), radius=int(37 * k), fill=white)
        for x0 in (40, 142):                         # its grips
            d.ellipse(B(x0, 104, x0 + 70, 194), fill=white)
        d.rounded_rectangle(B(78, 104, 96, 158), radius=int(4 * k), fill=colour)    # the d-pad
        d.rounded_rectangle(B(60, 122, 114, 140), radius=int(4 * k), fill=colour)
        for x, y in ((170, 112), (192, 132), (148, 132), (170, 152)):
            d.ellipse(B(x - 10, y - 10, x + 10, y + 10), fill=colour)
    else:                                           # a tab added by hand: its first letter
        try:
            font = ImageFont.truetype(FONT_BOLD, int(120 * k))
        except OSError:
            font = ImageFont.load_default()
        d.text((S / 2, S / 2), (name[:1] or "?").upper(), font=font, fill=white, anchor="mm")
    return im.resize((size, size), Image.LANCZOS)
