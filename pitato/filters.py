"""Photo filters, for a copy of a picture."""


# ---- photo filters: the same looks as PiE-ink's camera -----------------------------
FILTERS = [("none", "Original"), ("bw", "B&W"), ("sepia", "Sepia"), ("warm", "Warm"),
           ("vivid", "Vivid"), ("blue", "Blue"), ("sketch", "Sketch"), ("trace", "Edge trace"),
           ("comic", "Comic"), ("pixel", "Pixel"), ("eink", "E-ink")]
FILTER_CSS = {      # colour filters: the CSS filter functions, in order
    "none": [], "bw": [("grayscale", 1), ("contrast", 1.15)],
    "sepia": [("sepia", 0.9), ("contrast", 1.05)],
    "warm": [("sepia", 0.3), ("saturate", 1.35), ("contrast", 1.05)],
    "vivid": [("saturate", 1.8), ("contrast", 1.15)],
    "blue": [("grayscale", 1), ("sepia", 0.9), ("hue-rotate", 175), ("saturate", 1.6)],
}


def _matrix(fn, v):
    """One CSS filter function as a 3x3 matrix and an offset (0-255)."""
    import math
    if fn in ("grayscale", "sepia"):
        a = 1 - max(0.0, min(1.0, v))
        if fn == "grayscale":
            return ((0.2126 + 0.7874 * a, 0.7152 - 0.7152 * a, 0.0722 - 0.0722 * a),
                    (0.2126 - 0.2126 * a, 0.7152 + 0.2848 * a, 0.0722 - 0.0722 * a),
                    (0.2126 - 0.2126 * a, 0.7152 - 0.7152 * a, 0.0722 + 0.9278 * a)), 0.0
        return ((0.393 + 0.607 * a, 0.769 - 0.769 * a, 0.189 - 0.189 * a),
                (0.349 - 0.349 * a, 0.686 + 0.314 * a, 0.168 - 0.168 * a),
                (0.272 - 0.272 * a, 0.534 - 0.534 * a, 0.131 + 0.869 * a)), 0.0
    if fn == "saturate":
        s = max(0.0, v)
        return ((0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s),
                (0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s),
                (0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s)), 0.0
    if fn == "hue-rotate":
        c, s = math.cos(math.radians(v)), math.sin(math.radians(v))
        return ((0.213 + c * 0.787 - s * 0.213, 0.715 - c * 0.715 - s * 0.715, 0.072 - c * 0.072 + s * 0.928),
                (0.213 - c * 0.213 + s * 0.143, 0.715 + c * 0.285 + s * 0.140, 0.072 - c * 0.072 - s * 0.283),
                (0.213 - c * 0.213 - s * 0.787, 0.715 - c * 0.715 + s * 0.715, 0.072 + c * 0.928 + s * 0.072)), 0.0
    if fn == "contrast":
        return ((v, 0, 0), (0, v, 0), (0, 0, v)), 127.5 * (1 - v)
    return ((1, 0, 0), (0, 1, 0), (0, 0, 1)), 0.0


def _working(img, most=960):
    """Drawn filters work at a modest size (quick on a Pi Zero), then go back up."""
    from PIL import Image
    if img.width <= most:
        return img, None
    return img.resize((most, max(1, round(img.height * most / img.width))), Image.LANCZOS), img.size


def _sketch(img):
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps
    work, size = _working(img)
    g = work.convert("L")
    blur = g.filter(ImageFilter.GaussianBlur(max(2.0, g.width / 80)))
    a, b = np.asarray(g, dtype=np.float32), np.asarray(blur, dtype=np.float32)
    dodge = np.clip(a * 255.0 / np.maximum(b, 1.0), 0, 255)          # pencil on paper
    out = Image.fromarray((255 - np.clip((255 - dodge) * 1.8, 0, 255)).astype("uint8"), "L")
    out = ImageOps.colorize(out, black=(46, 42, 50), white=(248, 246, 238))
    return out.resize(size, Image.LANCZOS) if size else out


def _trace(img):
    import numpy as np
    from PIL import Image, ImageFilter
    work, size = _working(img)
    g = work.convert("L").filter(ImageFilter.GaussianBlur(max(0.8, work.width / 700)))
    q = np.pad(np.asarray(g, dtype=np.float32), 1, mode="edge")
    gx = (q[:-2, 2:] + 2 * q[1:-1, 2:] + q[2:, 2:]) - (q[:-2, :-2] + 2 * q[1:-1, :-2] + q[2:, :-2])
    gy = (q[2:, :-2] + 2 * q[2:, 1:-1] + q[2:, 2:]) - (q[:-2, :-2] + 2 * q[:-2, 1:-1] + q[:-2, 2:])
    mag = np.hypot(gx, gy)
    top = max(float(np.percentile(mag, 98)), 90.0)
    out = Image.fromarray((np.clip(mag / top, 0, 1) ** 1.3 * 255).astype("uint8"), "L").convert("RGB")
    return out.resize(size, Image.LANCZOS) if size else out


def _comic(img):
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
    work, size = _working(img, most=800)
    smooth = work.filter(ImageFilter.MedianFilter(5))
    g = smooth.convert("L")
    around = g.filter(ImageFilter.BoxBlur(max(3, work.width // 110)))
    ink = ImageChops.subtract(around, g).point(lambda v: 0 if v > 10 else 255)
    ink = ink.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    base = ImageEnhance.Color(ImageOps.posterize(smooth, 3)).enhance(1.4)
    out = ImageChops.multiply(base, Image.merge("RGB", (ink, ink, ink)))
    return out.resize(size, Image.LANCZOS) if size else out


def _blocks(img, across):
    w, h = img.size
    block = max(1, round(w / max(8, min(across, w))))
    across = max(1, w // block)
    return block, across, max(1, round(h * across / w))


def _pixel(img, across=96, colours=24):
    from PIL import Image
    block, across, down = _blocks(img, across)
    small = img.resize((across, down), Image.BOX)
    try:
        small = small.quantize(colors=colours, dither=getattr(getattr(Image, "Dither", Image), "NONE", 0))
    except (TypeError, ValueError):
        small = small.quantize(colors=colours)
    return small.convert("RGB").resize((across * block, down * block), Image.NEAREST)


def _eink(img, across=400):
    from PIL import Image, ImageOps
    block, across, down = _blocks(img, across)
    g = ImageOps.autocontrast(img.convert("L").resize((across, down), Image.LANCZOS), cutoff=1)
    dots = g.convert("1", dither=Image.FLOYDSTEINBERG).convert("L")
    dots = dots.resize((across * block, down * block), Image.NEAREST)
    return ImageOps.colorize(dots, black=(34, 34, 38), white=(226, 224, 216))


def apply_filter(img, fid):
    """The picture with a filter on (RGB). Small pictures (the preview) get the
    drawn filters scaled to match how they'll look on the full-size copy."""
    img = img.convert("RGB")
    drawn = {"sketch": _sketch, "trace": _trace, "comic": _comic, "pixel": _pixel, "eink": _eink}
    if fid in drawn:
        return drawn[fid](img)
    for fn, v in FILTER_CSS.get(fid, []):
        m, off = _matrix(fn, float(v))
        img = img.convert("RGB", (m[0][0], m[0][1], m[0][2], off,
                                  m[1][0], m[1][1], m[1][2], off,
                                  m[2][0], m[2][1], m[2][2], off))
    return img
