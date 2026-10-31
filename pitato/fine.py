"""Drawing finer than the menus' own pixels, for a big screen. On a 4K TV the menus are 960 x 540 of their pixels, each
shown 4 x 4: blocky. Drawn finer, each of their pixels is SCALE x SCALE of the picture's (2 x 2 there), so text, lines,
curves and pictures are sharp, and nothing moves: the layout is the menus' as ever.

The screens draw as they always have, through Image and ImageDraw from here instead of PIL's own. At SCALE 1 (the GPi
Case, a slow Pi, a small screen) they are PIL's, untouched. Above it, a picture made here (Fine) says it's its usual
size, keeps SCALE times as many pixels each way, and ImageDraw on it draws at that detail: places and sizes in the
menus' pixels, fonts SCALE times bigger, text measured with the usual ones (so it's laid out just as before). A plain
picture pasted onto it (a sim's dots, a photo made at the usual size) is enlarged to fit, pixel for pixel. Anything
else asked of it is done on its usual-size copy: right, plain, just not sharper. (PIL itself is only imported when
something's drawn: media mode says it's unavailable without it, as ever.)"""
SCALE = 1                       # the picture's pixels to each of the menus', each way (media mode sets it: Framebuffer.s)


def set_scale(s):
    global SCALE
    SCALE = max(1, int(s or 1))


def scale():
    return SCALE


def _P():
    from PIL import Image
    return Image


def is_picture(x):
    """A picture: a Fine one, or PIL's."""
    return isinstance(x, Fine) or isinstance(x, _P().Image)


class Fine:
    """A picture its size says (the menus' pixels), with s x s of its own pixels to each of them (pic)."""
    __slots__ = ("pic", "s")

    def __init__(self, pic, s):
        self.pic, self.s = pic, s

    def __repr__(self):
        return f"<Fine {self.mode} {self.width}x{self.height} x{self.s}>"

    # -- what it says it is ---------------------------------------------------------------------------------------
    @property
    def size(self):
        return self.pic.width // self.s, self.pic.height // self.s

    @property
    def width(self):
        return self.pic.width // self.s

    @property
    def height(self):
        return self.pic.height // self.s

    @property
    def mode(self):
        return self.pic.mode

    @property
    def info(self):
        return self.pic.info

    def logical(self):
        """Its usual-size copy, a plain picture: each of its pixels the average of its own s x s."""
        if self.s == 1:
            return self.pic
        if self.pic.mode in ("1", "P", "I", "F"):
            return self.pic.resize(self.size, _P().NEAREST)
        return self.pic.reduce(self.s)

    @property
    def __array_interface__(self):            # (numpy sees its usual-size pixels)
        return self.logical().__array_interface__

    def __getattr__(self, name):                 # anything else: done on its usual-size copy
        if name.startswith("_") or name in ("im", "readonly", "pyaccess", "palette"):
            raise AttributeError(name)           # (PIL's own insides: never a copy's, quietly)
        return getattr(self.logical(), name)

    # -- the same picture, changed -----------------------------------------------------------------------------------
    def _wrap(self, pic):
        return Fine(pic, self.s)

    def copy(self):
        return self._wrap(self.pic.copy())

    def convert(self, mode=None, *a, **k):
        return self._wrap(self.pic.convert(mode, *a, **k))

    def crop(self, box=None):
        if box is None:
            return self.copy()
        return self._wrap(self.pic.crop(tuple(round(v * self.s) for v in box)))

    def resize(self, size, resample=None, box=None, reducing_gap=None):
        k = {} if resample is None else {"resample": resample}
        if box is not None:
            k["box"] = tuple(v * self.s for v in box)
        if reducing_gap is not None:
            k["reducing_gap"] = reducing_gap
        return self._wrap(self.pic.resize((max(1, round(size[0] * self.s)), max(1, round(size[1] * self.s))), **k))

    def reduce(self, factor, box=None):
        return self._wrap(self.pic.reduce(factor, None if box is None else tuple(v * self.s for v in box)))

    def transpose(self, method):
        return self._wrap(self.pic.transpose(method))

    def rotate(self, angle, resample=0, expand=0, center=None, translate=None, fillcolor=None):
        return self._wrap(self.pic.rotate(
            angle, resample, expand, center=None if center is None else (center[0] * self.s, center[1] * self.s),
            translate=None if translate is None else (translate[0] * self.s, translate[1] * self.s),
            fillcolor=fillcolor))

    def filter(self, f):
        return self._wrap(self.pic.filter(scaled_filter(f, self.s)))

    def point(self, *a, **k):
        return self._wrap(self.pic.point(*a, **k))

    def split(self):
        return tuple(self._wrap(b) for b in self.pic.split())

    def getchannel(self, channel):
        return self._wrap(self.pic.getchannel(channel))

    def getbbox(self, *a, **k):
        box = self.pic.getbbox(*a, **k)
        if box is None:
            return None
        s = self.s
        return box[0] // s, box[1] // s, -(-box[2] // s), -(-box[3] // s)

    def getpixel(self, xy):
        return self.pic.getpixel((int(xy[0]) * self.s, int(xy[1]) * self.s))

    def getextrema(self):
        return self.pic.getextrema()

    def tobytes(self, *a, **k):
        return self.logical().tobytes(*a, **k)

    def save(self, fp, format=None, **params):
        """Saved at its usual size (the web page's copy of the screen, a picture kept): as it'd be at SCALE 1."""
        return self.logical().save(fp, format, **params)

    def load(self):
        return self.pic.load()

    # -- the same picture, changed in place --------------------------------------------------------------------------
    def paste(self, im, box=None, mask=None):
        s = self.s
        if box is not None and mask is None and is_picture(box):
            box, mask = None, box                      # (PIL's way: the box given is the mask)
        if box is None:
            box = (0, 0)
        if len(box) == 4:
            fbox = tuple(round(v * s) for v in box)
        else:
            fbox = (round(box[0] * s), round(box[1] * s))
        if mask is not None:
            mask = finer(mask, s)
        if is_picture(im):
            im = finer(im, s)
            if len(fbox) == 4 and (fbox[2] - fbox[0], fbox[3] - fbox[1]) != im.size:
                fbox = fbox[:2]                        # (a box its size, as PIL wants: just where it goes)
        self.pic.paste(im, fbox, mask)

    def alpha_composite(self, im, dest=(0, 0), source=(0, 0)):
        s = self.s
        source = tuple(round(v * s) for v in source)
        self.pic.alpha_composite(finer(im, s), (round(dest[0] * s), round(dest[1] * s)), source)

    def putalpha(self, alpha):
        self.pic.putalpha(alpha if isinstance(alpha, int) else finer(alpha, self.s))

    def thumbnail(self, size, resample=None, reducing_gap=2.0):
        k = {} if resample is None else {"resample": resample}
        self.pic.thumbnail((size[0] * self.s, size[1] * self.s), reducing_gap=reducing_gap, **k)
        w, h = self.pic.size                           # (whole pixels of the menus': trimmed to fit)
        if w % self.s or h % self.s:
            self.pic = self.pic.crop((0, 0, w - w % self.s or w, h - h % self.s or h))

    def putpixel(self, xy, value):
        s = self.s
        self.pic.paste(value, (int(xy[0]) * s, int(xy[1]) * s, int(xy[0]) * s + s, int(xy[1]) * s + s))


def finer(im, s, resample=None):
    """A picture at s times the detail, as a plain PIL one (s times its size): a Fine one's own pixels (enlarged or
    reduced from another scale's), a plain one enlarged, pixel for pixel unless resample says otherwise."""
    P = _P()
    if isinstance(im, Fine):
        if im.s == s:
            return im.pic
        return im.pic.resize((im.pic.width * s // im.s, im.pic.height * s // im.s), P.NEAREST if s > im.s
                             else P.BOX)
    if s == 1:
        return im
    return im.resize((im.width * s, im.height * s), P.NEAREST if resample is None else resample)


def made_fine(pic, s=None):
    """A plain picture already s times the detail (a photo made that big): as a Fine one, its size pic's over s."""
    s = SCALE if s is None else s
    if s == 1:
        return pic
    w, h = pic.size
    if w % s or h % s:
        pic = pic.crop((0, 0, w - w % s, h - h % s))
    return Fine(pic, s)


def enlarged(pic, resample=None):
    """A plain picture made Fine at SCALE, enlarged to it (pixel for pixel, or as resample says); itself at SCALE 1."""
    if SCALE == 1 or isinstance(pic, Fine):
        return pic
    return Fine(finer(pic, SCALE, resample), SCALE)


def plain(im):
    """A plain PIL picture of it (its usual size)."""
    return im.logical() if isinstance(im, Fine) else im


def detail(im):
    """How many of its own pixels it has to each of the menus' (1 for a plain picture)."""
    return im.s if isinstance(im, Fine) else 1


def scaled_filter(f, s):
    """A blur as wide in the menus' pixels as it was: s times as many of the picture's."""
    if s == 1:
        return f
    from PIL import ImageFilter
    for kind in ("GaussianBlur", "BoxBlur"):
        k = getattr(ImageFilter, kind, None)
        if k is not None and isinstance(f, k):
            r = f.radius
            return k(tuple(v * s for v in r) if isinstance(r, (tuple, list)) else r * s)
    return f


def _same_detail(args):
    """The pictures among args at the finest detail any has (plain PIL ones), and that detail."""
    s = max((detail(a) for a in args if is_picture(a)), default=1)
    return s, [finer(a, s) if is_picture(a) else a for a in args]


def _wrapped(fn):
    """PIL's fn, given Fine pictures too: done at their detail, a Fine picture back if it gives one."""
    def call(*args, **kw):
        if not any(isinstance(a, Fine) for a in list(args) + list(kw.values())):
            return fn(*args, **kw)
        s, args = _same_detail(list(args))
        kw = {k: finer(v, s) if is_picture(v) else v for k, v in kw.items()}
        out = fn(*args, **kw)
        return Fine(out, s) if isinstance(out, _P().Image) else out
    return call


class _Module:
    """One of PIL's modules, its functions taking Fine pictures too (those named in fine, done here)."""

    def __init__(self, name, fine=()):
        self._name, self._fine = name, dict(fine)

    def _mod(self):
        import importlib
        return importlib.import_module("PIL." + self._name)

    def __getattr__(self, name):
        if name in self._fine:
            return self._fine[name]
        got = getattr(self._mod(), name)
        return _wrapped(got) if callable(got) and not isinstance(got, type) and self._name != "Image" else got


# ---- PIL's Image, the Fine way ---------------------------------------------------------------------------------------
def _new(mode, size, color=0):
    P = _P()
    if SCALE == 1:
        return P.new(mode, size, color)
    return Fine(P.new(mode, (int(size[0]) * SCALE, int(size[1]) * SCALE), color), SCALE)


def _picture_fn(name):
    def call(*args, **kw):
        fn = getattr(_P(), name)
        return _wrapped(fn)(*args, **kw)
    return call


Image = _Module("Image", {"new": _new, "composite": _picture_fn("composite"),
                          "alpha_composite": _picture_fn("alpha_composite"), "blend": _picture_fn("blend"),
                          "merge": lambda mode, bands: _wrapped(_P().merge)(mode, list(bands))})
ImageChops = _Module("ImageChops")


# ---- ImageDraw, the Fine way -----------------------------------------------------------------------------------------
_fonts = {}                     # (a font, s) -> it s times bigger


def big_font(font, s):
    """The font s times its size (None if it can't be: PIL's own little bitmap one)."""
    if font is None or s == 1:
        return font
    key = (id(font), s)
    got = _fonts.get(key)
    if got is not None and got[0] is font:
        return got[1]
    size = getattr(font, "size", None)
    try:
        big = font.font_variant(size=round(size * s)) if size else None
    except (AttributeError, OSError, TypeError, ValueError):
        big = None
    if len(_fonts) > 400:
        _fonts.clear()
    _fonts[key] = (font, big)
    return big


def _flat(xy):
    """[x0, y0, x1, y1, ...] from any of PIL's ways of giving points."""
    out = []
    for v in xy:
        if isinstance(v, (tuple, list)):
            out.extend(v)
        else:
            out.append(v)
    return out


_measure = []                   # a 1 x 1 picture's ImageDraw: text measured as it is at SCALE 1


def measurer():
    if not _measure:
        from PIL import ImageDraw
        _measure.append(ImageDraw.Draw(_P().new("L", (1, 1))))
    return _measure[0]


class FineDraw:
    """ImageDraw on a Fine picture: where and how big in the menus' pixels, drawn s times as finely."""

    def __init__(self, fine, mode=None):
        from PIL import ImageDraw
        self.fine, self.s = fine, fine.s
        self.d = ImageDraw.Draw(fine.pic, mode)

    def __getattr__(self, name):
        return getattr(self.d, name)

    # (a box's corners are whole pixels, both in it: its last pixel's s of them too)
    def _box(self, xy):
        v, s = _flat(xy), self.s
        x0, y0, x1, y1 = v[0], v[1], v[2], v[3]
        return [x0 * s, y0 * s, x1 * s + s - 1, y1 * s + s - 1]

    def _points(self, xy):
        v, s = _flat(xy), self.s
        h = (s - 1) / 2                                 # (each point the middle of its pixel's s x s)
        return [(v[i] * s + h, v[i + 1] * s + h) for i in range(0, len(v) - 1, 2)]

    def _w(self, width):
        return self.s if not width else max(1, round(width * self.s))

    def rectangle(self, xy, fill=None, outline=None, width=1):
        return self.d.rectangle(self._box(xy), fill, outline, self._w(width))

    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, **k):
        return self.d.rounded_rectangle(self._box(xy), radius * self.s, fill, outline, self._w(width), **k)

    def ellipse(self, xy, fill=None, outline=None, width=1):
        return self.d.ellipse(self._box(xy), fill, outline, self._w(width))

    def arc(self, xy, start, end, fill=None, width=1):
        return self.d.arc(self._box(xy), start, end, fill, self._w(width))

    def pieslice(self, xy, start, end, fill=None, outline=None, width=1):
        return self.d.pieslice(self._box(xy), start, end, fill, outline, self._w(width))

    def chord(self, xy, start, end, fill=None, outline=None, width=1):
        return self.d.chord(self._box(xy), start, end, fill, outline, self._w(width))

    def line(self, xy, fill=None, width=0, joint=None):
        return self.d.line(self._points(xy), fill, self._w(width), joint)

    def polygon(self, xy, fill=None, outline=None, width=1):
        return self.d.polygon(self._points(xy), fill, outline, self._w(width))

    def point(self, xy, fill=None):
        s = self.s
        for x, y in zip(*[iter(_flat(xy))] * 2):
            self.d.rectangle((x * s, y * s, x * s + s - 1, y * s + s - 1), fill)

    def bitmap(self, xy, bitmap, fill=None):
        s = self.s
        self.d.bitmap((xy[0] * s, xy[1] * s), finer(bitmap, s), fill)

    # -- text: drawn with the font s times bigger, measured with its own ------------------------------------------
    def _font(self, font):
        return font if font is not None else self.d.getfont()

    def text(self, xy, text, fill=None, font=None, anchor=None, spacing=4, align="left", direction=None,
             features=None, language=None, stroke_width=0, stroke_fill=None, **k):
        s = self.s
        f = self._font(font)
        big = big_font(f, s)
        if big is None:                                # (no bigger one: drawn as usual, then enlarged into place)
            return self._text_plain(xy, text, fill, f, anchor, spacing, align, stroke_width)
        extra = {}
        if direction is not None:
            extra["direction"] = direction
        if features is not None:
            extra["features"] = features
        if language is not None:
            extra["language"] = language
        if stroke_width:
            extra["stroke_width"] = round(stroke_width * s)
            extra["stroke_fill"] = stroke_fill
        extra.update(k)
        return self.d.text((xy[0] * s, xy[1] * s), text, fill=fill, font=big, anchor=anchor, spacing=spacing * s,
                           align=align, **extra)

    def _text_plain(self, xy, text, fill, font, anchor, spacing, align, stroke_width):
        from PIL import ImageDraw
        l, t, r, b = measurer().textbbox(xy, text, font=font, anchor=anchor, spacing=spacing, align=align,
                                         stroke_width=stroke_width)
        mask = _P().new("L", (max(1, r - l), max(1, b - t)), 0)
        ImageDraw.Draw(mask).text((xy[0] - l, xy[1] - t), text, fill=255, font=font, anchor=anchor, spacing=spacing,
                                  align=align, stroke_width=stroke_width)
        s = self.s
        self.d.bitmap((l * s, t * s), finer(mask, s), fill)

    def multiline_text(self, xy, text, *a, **k):
        return self.text(xy, text, *a, **k)

    def textlength(self, text, font=None, *a, **k):
        return measurer().textlength(text, font=self._font(font), *a, **k)

    def textbbox(self, xy, text, font=None, *a, **k):
        return measurer().textbbox(xy, text, font=self._font(font), *a, **k)

    def multiline_textbbox(self, xy, text, font=None, *a, **k):
        return measurer().multiline_textbbox(xy, text, font=self._font(font), *a, **k)


def _draw(im, mode=None):
    if isinstance(im, Fine):
        return FineDraw(im, mode)
    from PIL import ImageDraw
    return ImageDraw.Draw(im, mode)


ImageDraw = _Module("ImageDraw", {"Draw": _draw})
