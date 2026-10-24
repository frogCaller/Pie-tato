"""Photos: thumbnails, a picture full screen, filters and deleting."""
import os
import threading
import time

from ..theme import ACCENT, BG, BODY, LINE, MUTED, PHOTO_BG, ROW, TEXT
from ..config import CACHE_DIR
from ..util import cache_name, in_home, pictures_dir, write_new
from ..library import SLIDESHOW_SECS
from ..filters import apply_filter, FILTER_CSS, FILTERS


class PhotoScreen:
    """Photos: thumbnails, a picture full screen, filters and deleting."""

    # -- photo thumbnails ----------------------------------------------------
    THUMB = (144, 108)

    def thumb(self, path):
        """Thumbnail from memory or disk cache, or None if not made yet."""
        im = self.thumbs.get(path)
        if im is not None:
            return im
        fn = os.path.join(CACHE_DIR, "thumbs", cache_name(path, ".jpg"))
        if os.path.exists(fn):
            from PIL import Image
            try:
                im = Image.open(fn)
                im.load()
                self.keep_thumb(path, im)
                return im
            except OSError:
                pass
        return None

    def has_thumb(self, path):
        return path in self.thumbs or os.path.exists(
            os.path.join(CACHE_DIR, "thumbs", cache_name(path, ".jpg")))

    def keep_thumb(self, path, im):
        self.thumbs[path] = im
        if len(self.thumbs) > 300:
            self.thumbs.pop(next(iter(self.thumbs)))

    def thumb_loop(self):
        from PIL import Image, ImageOps
        os.makedirs(os.path.join(CACHE_DIR, "thumbs"), exist_ok=True)
        failed = set()
        pi = self.tab_index("photos")
        while self.active:
            if self.proc_owns_screen() or self.view not in ("list", "help"):
                time.sleep(0.5)
                continue
            items = self.tab_items(pi)
            start = self.tops.get(pi, 0) * self.grid_cols()
            order = list(range(start, len(items))) + list(range(0, start))
            todo = next((items[k]["src"] for k in order
                         if items[k]["src"] not in failed and not self.has_thumb(items[k]["src"])),
                        None)
            if todo is None:
                time.sleep(1)
                continue
            try:
                im = Image.open(todo)
                im.draft("RGB", (self.THUMB[0] * 2, self.THUMB[1] * 2))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im = ImageOps.fit(im, self.THUMB, Image.BILINEAR)
                im.save(os.path.join(CACHE_DIR, "thumbs", cache_name(todo, ".jpg")), quality=85)
                self.keep_thumb(todo, im)
                if self.tab == pi:
                    self.dirty = True
            except Exception:
                failed.add(todo)

    # photos
    def open_photo(self, paths, i):
        self.close_viewer()
        self.v = {"type": "photo", "items": paths, "i": i, "zoom": 1, "rot": 0,
                  "img": None, "img_for": None, "cx": 0, "cy": 0,
                  "slideshow": False, "next_t": 0,
                  "edit": False, "fi": 0, "prev": {}, "confirm": False, "busy": None,
                  "changed": False}
        self.view = "photo"
        self.dirty = True

    def photo_image(self):
        from PIL import Image, ImageOps
        v = self.v
        key = (v["items"][v["i"]], v["rot"])
        if v["img_for"] != key:
            v["img_for"] = key
            try:
                im = Image.open(key[0])
                im.draft("RGB", (1280, 960))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((1600, 1200))
                if v["rot"]:
                    im = im.rotate(-90 * v["rot"], expand=True)
            except Exception:
                im = None
            v["img"] = im
            if im:
                v["cx"], v["cy"] = im.width / 2, im.height / 2
        return v["img"]

    def photo_step(self, d):
        v = self.v
        v["i"] = (v["i"] + d) % len(v["items"])
        v["zoom"], v["rot"] = 1, 0
        self.dirty = True

    PREVIEW_STRIP = 52                  # the filter names under the picture while editing

    def photo_preview(self, size):
        """The picture as it's shown, with the chosen filter on (kept per filter).
        Worked out on a thread — the drawn filters take a moment on a Pi Zero —
        showing the last one meanwhile."""
        from PIL import Image
        v = self.v
        im = self.photo_image()
        if im is None:
            return None
        fid = FILTERS[v["fi"]][0]
        key = (v["img_for"], fid, size)
        if key in v["prev"]:
            v["shown"] = v["prev"][key]
            return v["shown"]
        if v.get("working") != key:
            v["working"] = key
            base = im.copy()
            base.thumbnail(size)

            def job():
                try:
                    if fid in FILTER_CSS:
                        out = apply_filter(base, fid)
                    else:                              # drawn: a smaller one, scaled up
                        small = base.copy()
                        small.thumbnail((400, 400))
                        out = apply_filter(small, fid).resize(base.size, Image.BILINEAR)
                except Exception:
                    out = base
                v["prev"][key] = out
                if v.get("working") == key:
                    v["working"] = None
                self.dirty = True
            threading.Thread(target=job, daemon=True, name="photo-preview").start()
        shown = v.get("shown")
        if shown is None or v.get("shown_for") != v["img_for"]:
            shown = im.copy()
            shown.thumbnail(size)
        v["shown_for"] = v["img_for"]
        return shown

    def photo_save_copy(self):
        """A: the filter (and the turn) onto the full-size picture, kept as a copy
        next to it — or in ~/Pictures for one outside your home folder."""
        v = self.v
        fid, label = FILTERS[v["fi"]]
        rot = v["rot"]
        if fid == "none" and not rot:
            self.toast("Pick a filter with ◀ ▶ first", 2)
            return
        src = v["items"][v["i"]]
        v["busy"] = "Saving…"

        def job():
            from PIL import Image, ImageOps
            import io
            try:
                im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
                if rot:
                    im = im.rotate(-90 * rot, expand=True)
                im = apply_filter(im, fid)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=92, optimize=True)
                folder = os.path.dirname(src) if in_home(src) else pictures_dir()
                stem = os.path.splitext(os.path.basename(src))[0]
                path = write_new(folder, f"{stem}-{fid if fid != 'none' else 'turned'}", ".jpg",
                                 buf.getvalue())
                if self.v is v:
                    v["items"].insert(v["i"], path)
                    v.update(edit=False, fi=0, rot=0, zoom=1, changed=True)
                self.last_shot = path
                self.toast(f"Saved {os.path.basename(path)}", 3)
            except Exception as ex:
                self.toast(f"Couldn't save it ({getattr(ex, 'strerror', None) or ex})"[:70], 4)
            finally:
                v["busy"] = None
                self.dirty = True
        threading.Thread(target=job, daemon=True, name="photo-save").start()

    def photo_delete(self):
        v = self.v
        v["confirm"] = False
        path = v["items"][v["i"]]
        if self.is_net(path):
            self.toast("It's on another computer: it can't be deleted from here", 4)
            return
        try:
            os.remove(path)
        except OSError as ex:
            self.toast(f"Couldn't delete it ({ex.strerror or ex})", 4)
            return
        v["items"].pop(v["i"])
        v["changed"] = True
        self.toast("Deleted", 2)
        if not v["items"]:
            self.photo_back()
            return
        v["i"] %= len(v["items"])
        v["zoom"], v["rot"] = 1, 0

    def press_photo(self, name, repeat):
        v = self.v
        if v["slideshow"]:
            v["slideshow"] = False
            self.dirty = True
            return None
        if v["busy"]:                                  # saving a copy: wait for it
            return None
        if v["confirm"]:                               # "Delete this picture?"
            if name == "a" and not repeat:
                self.photo_delete()
            elif name in ("b", "select") and not repeat:
                v["confirm"] = False
            self.dirty = True
            return None
        if v["edit"]:                                  # picking a filter
            if name in ("left", "right") and not repeat:
                v["fi"] = (v["fi"] + (1 if name == "right" else -1)) % len(FILTERS)
            elif name == "y" and not repeat:
                v["rot"] = (v["rot"] + 1) % 4
            elif name == "a" and not repeat:
                self.photo_save_copy()
            elif name in ("b", "x") and not repeat:
                v.update(edit=False, fi=0)
            self.dirty = True
            return None
        if name == "x" and not repeat:
            v.update(edit=True, fi=0, zoom=1)
            self.dirty = True
            return None
        if name == "select" and not repeat:
            if in_home(v["items"][v["i"]]):
                v["confirm"] = True
            else:
                self.toast("Only pictures in your home folder can be deleted here", 3)
            self.dirty = True
            return None
        im = self.photo_image()
        zoomed = v["zoom"] > 1 and im is not None
        if name == "b":
            self.photo_back()
        elif name in ("l", "r") or (name in ("left", "right") and not zoomed):
            self.photo_step(-1 if name in ("l", "left") else 1)
        elif name in ("left", "right", "up", "down") and zoomed:
            AW, AH = self.fb.w, self.fb.h - self.FOOTER
            s = min(AW / im.width, AH / im.height) * v["zoom"]
            dx = {"left": -1, "right": 1}.get(name, 0) * AW * 0.25 / s
            dy = {"up": -1, "down": 1}.get(name, 0) * AH * 0.25 / s
            v["cx"], v["cy"] = v["cx"] + dx, v["cy"] + dy
        elif name == "a" and not repeat:
            v["zoom"] = {1: 2, 2: 4}.get(v["zoom"], 1)
            if v["zoom"] == 1 and im:
                v["cx"], v["cy"] = im.width / 2, im.height / 2
        elif name == "y" and not repeat:
            v["rot"] = (v["rot"] + 1) % 4
            v["zoom"] = 1
        elif name == "start":
            v["slideshow"], v["zoom"] = True, 1
            v["next_t"] = time.monotonic() + SLIDESHOW_SECS
        self.dirty = True
        return None

    def photo_back(self):
        v = self.v
        path = v["items"][v["i"]] if v.get("items") else None
        ttype = self.tab_type()
        if v.get("changed"):                           # deleted or added: the list again
            if ttype == "photos":
                self.load_tab(self.tab)
            elif ttype == "browser":
                self.browse(self.cwd, select=path)
        if ttype == "photos" and path:
            items = self.tab_items()
            self.sels[self.tab] = next((k for k, x in enumerate(items) if x["src"] == path),
                                       min(self.sels.get(self.tab, 0), max(len(items) - 1, 0)))
        self.last_shot = None
        self.close_viewer()

    def render_photo(self):
        from PIL import Image
        F = self.fonts
        v = self.v
        img, d = self.canvas(PHOTO_BG)
        W, H = self.fb.w, self.fb.h
        full = v["slideshow"]
        AW, AH = W, (H if full else H - self.FOOTER)
        im = self.photo_image()
        if v["edit"]:
            AH -= self.PREVIEW_STRIP
        if im is None:
            d.text((W / 2, AH / 2), "Can't show this picture", font=F["big"], fill=TEXT, anchor="mm")
        elif v["edit"]:
            pv = self.photo_preview((AW, AH))
            img.paste(pv, ((AW - pv.width) // 2, (AH - pv.height) // 2))
        else:
            s = min(AW / im.width, AH / im.height) * v["zoom"]
            vw, vh = AW / s, AH / s
            hw, hh = min(vw, im.width) / 2, min(vh, im.height) / 2
            v["cx"] = max(hw, min(v["cx"], im.width - hw))
            v["cy"] = max(hh, min(v["cy"], im.height - hh))
            box = (int(v["cx"] - hw), int(v["cy"] - hh), int(v["cx"] + hw), int(v["cy"] + hh))
            part = im.crop(box)
            size = (max(int(part.width * s), 1), max(int(part.height * s), 1))
            part = part.resize(size, Image.BILINEAR)
            img.paste(part, ((AW - size[0]) // 2, (AH - size[1]) // 2))
        if not full:
            pos = f"{v['i'] + 1} of {len(v['items'])}"
            name = os.path.basename(v["items"][v["i"]])
            if v["edit"]:                              # the filters, the chosen one in the middle
                y0 = AH
                d.rectangle((0, y0, W, y0 + self.PREVIEW_STRIP), fill=BG)
                widths = [d.textlength(lab, font=F["small"]) + 28 for _, lab in FILTERS]
                x = W / 2 - widths[v["fi"]] / 2 - sum(widths[:v["fi"]]) - 8 * v["fi"]
                for k, (_, lab) in enumerate(FILTERS):
                    on = k == v["fi"]
                    if x + widths[k] > 0 and x < W:
                        d.rounded_rectangle((x, y0 + 11, x + widths[k], y0 + 41), radius=15,
                                            fill=ACCENT if on else ROW)
                        d.text((x + widths[k] / 2, y0 + 26), lab + ("…" if on and v.get("working") else ""),
                               font=F["small"], fill=BG if on else BODY, anchor="mm")
                    x += widths[k] + 8
                hints = [("◀▶", "Filter"), ("Y", "Turn"), ("A", v["busy"] or "Save copy"),
                         ("B", "Cancel")]
            elif v["zoom"] > 1:
                hints = [("A", f"Zoom {v['zoom']}x"), ("PAD", "Move"), ("L R", "Prev/next"),
                         ("B", "Back")]
            else:
                hints = [("◀▶", "Next"), ("A", "Zoom"), ("X", "Filters"), ("SEL", "Delete"),
                         ("START", "Show"), ("B", "Back")]
            self.footer(d, hints, right=pos if not v["edit"] else None)
            if v["confirm"]:                           # are you sure?
                cw, ch = 420, 150
                cx0, cy0 = (W - cw) / 2, (AH - ch) / 2
                d.rounded_rectangle((cx0 - 2, cy0 - 2, cx0 + cw + 2, cy0 + ch + 2), radius=16, fill=LINE)
                d.rounded_rectangle((cx0, cy0, cx0 + cw, cy0 + ch), radius=15, fill=BG)
                d.text((W / 2, cy0 + 40), "Delete this picture?", font=F["big"], fill=TEXT, anchor="mm")
                d.text((W / 2, cy0 + 76), self.fit(d, name, F["small"], cw - 40), font=F["small"],
                       fill=BODY, anchor="mm")
                d.text((W / 2, cy0 + 102), "It can't be undone.", font=F["small"], fill=MUTED, anchor="mm")
                self.footer(d, [("A", "Delete"), ("B", "Keep")])
            label = self.fit(d, name, F["small"], W - 80)
            lw = d.textlength(label, font=F["small"]) + 24
            d.rounded_rectangle((12, 12, 12 + lw, 40), radius=14, fill=BG)
            d.text((24, 26), label, font=F["small"], fill=BODY, anchor="lm")
        self.fb.show(img)
