"""A drawing from the web page's Draw tab: on the whole screen until B."""
import io

from ..theme import PHOTO_BG
from ..library import LISTEN_KINDS

SKETCH_BYTES = 8 << 20                  # a drawing, at most (a PNG of a 1080p screen is far less)
SKETCH_PIXELS = 4096 * 4096             # ...and its size: anything bigger isn't one
SKETCH_SAYS = "A drawing from the web page. B goes back"


def sketch_image(data):
    """The Draw tab's drawing (a PNG or a JPEG) as an RGB picture, any see-through parts white like the
    page's paper. ValueError if it isn't a picture. (Opened on the web page's thread, not the screen's.)"""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        if im.format not in ("PNG", "JPEG") or im.width * im.height > SKETCH_PIXELS:
            raise ValueError
        im.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise ValueError("That isn't a drawing") from None
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        im = im.convert("RGBA")
        paper = Image.new("RGB", im.size, (255, 255, 255))
        paper.paste(im, mask=im.getchannel("A"))
        return paper
    return im.convert("RGB")


class SketchScreen:
    """A drawing from the web page's Draw tab, on the whole screen: B goes back to where you were.
    The next one from the page (each stroke, with Live on) takes its place."""

    def web_sketch(self, im):
        if not hasattr(im, "size"):
            return {"error": "That isn't a drawing"}
        if not self.web_ready():
            return {"error": "There's no screen to show it on"}
        if self.view != "sketch":
            self.sketch_from = self.view
            self.toast(SKETCH_SAYS, 4)
        self.sketch, self.sketch_fit = im, None
        self.view = "sketch"
        self.dirty = True
        return {"ok": True}

    def press_sketch(self, name, repeat):
        if name == "b" and not repeat:
            self.sketch_close()
        return None

    def sketch_close(self):
        back = self.sketch_from
        if back == "now" and not (self.proc and self.kind in LISTEN_KINDS):
            back = "list"                              # (the song it was showing has finished)
        self.view = back if back in ("home", "list", "now") else "list"
        self.sketch = self.sketch_fit = None
        if self.msg == SKETCH_SAYS:
            self.msg = None
        self.dirty = True

    def sketch_picture(self):
        """The drawing at the screen's size, made once for each drawing. (The page draws it that size: one
        drawn for another screen is scaled to fit.)"""
        from PIL import Image
        W, H = self.fb.w, self.fb.h
        im, fit = self.sketch, self.sketch_fit
        if fit is None or fit[0] is not im or fit[1] != (W, H):
            if im.size == (W, H):
                pic = im
            else:
                k = min(W / im.width, H / im.height)
                size = (max(1, round(im.width * k)), max(1, round(im.height * k)))
                pic = Image.new("RGB", (W, H), PHOTO_BG)
                pic.paste(im.resize(size, Image.LANCZOS if k < 1 else Image.BILINEAR),
                          ((W - size[0]) // 2, (H - size[1]) // 2))
            self.sketch_fit = fit = (im, (W, H), pic)
        return fit[2]

    def render_sketch(self):
        from PIL import ImageDraw
        if self.sketch is None:                        # (gone already: where it was, then)
            self.sketch_close()
            return self.flush()
        img = self.sketch_picture()
        if self.msg:                                   # (on a copy: the drawing stays as it came)
            img = img.copy()
            self.msg_pill(ImageDraw.Draw(img))
        self.fb.show(img)
