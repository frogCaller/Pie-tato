"""PDFs, documents and text, to read."""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import threading

from ..theme import BG, BODY, MUTED, PHOTO_BG, TEXT
from ..config import CACHE_DIR
from ..util import cache_name
from ..library import TEXT_LIMIT
from ..documents import doc_text


class ReadingScreen:
    """PDFs, documents and text, to read."""

    # pdfs
    def open_pdf(self, path, title=None):
        self.close_viewer()
        try:
            r = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=20)
            pages = int(re.search(r"^Pages:\s+(\d+)", r.stdout, re.M).group(1))
        except Exception:
            self.toast("Can't open this PDF (is poppler-utils installed?)")
            return
        self.v = {"type": "pdf", "path": path, "title": title or os.path.basename(path),
                  "page": 1, "pages": pages, "fit": "width", "scroll": 0,
                  "zoom": 1.0, "sx": 0,
                  "cache": {}, "tmp": tempfile.mkdtemp(prefix="pitato-pdf-")}
        self.view = "pdf"
        self.dirty = True

    def pdf_image(self, page=None):
        from PIL import Image
        v = self.v
        page = page or v["page"]
        key = (page, v["fit"], v["zoom"])
        if key not in v["cache"]:
            W, H = self.fb.w, self.fb.h - self.FOOTER
            size = (["-scale-to-x", str(int(W * v["zoom"])), "-scale-to-y", "-1"]
                    if v["fit"] == "width" else ["-scale-to-x", "-1", "-scale-to-y", str(H)])
            out = os.path.join(v["tmp"], f"p{page}{v['fit'][0]}{int(v['zoom'] * 100)}")
            try:
                subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile",
                                "-png", "-aa", "yes", "-aaVector", "yes"] + size
                               + [v["path"], out], timeout=60, check=True,
                               capture_output=True)
                im = Image.open(out + ".png").convert("RGB")
                os.remove(out + ".png")
            except Exception:
                im = None
            v["cache"][key] = im
            if len(v["cache"]) > 6:
                v["cache"].pop(next(iter(v["cache"])))
        return v["cache"][key]

    def pdf_goto(self, page, at_bottom=False):
        v = self.v
        page = max(1, min(page, v["pages"]))
        if page == v["page"]:
            return
        self.render_wait(v["title"], f"Page {page}")
        v["page"] = page
        v["scroll"] = 0
        if at_bottom:
            im = self.pdf_image()
            v["scroll"] = max(im.height - (self.fb.h - self.FOOTER), 0) if im else 0
        self.dirty = True

    # documents
    def open_doc(self, path):
        if shutil.which("soffice"):
            pdf = os.path.join(CACHE_DIR, "docs", cache_name(path, ".pdf"))
            if os.path.exists(pdf):
                self.open_pdf(pdf, os.path.basename(path))
                return
            self.close_viewer()
            self.v = {"type": "wait", "title": os.path.basename(path), "src": path,
                      "status": "Converting (the first time takes a while)", "result": None}
            self.view = "wait"
            self.dirty = True
            threading.Thread(target=self.convert_doc, args=(self.v, path, pdf),
                             daemon=True).start()
            return
        try:
            self.open_text(path, text=doc_text(path))
        except Exception:
            ext = os.path.splitext(path)[1].lower()
            self.toast("Install LibreOffice to open " + ext + " files" if ext in (".doc", ".xls", ".ppt")
                       else "Couldn't read this document")

    def convert_doc(self, v, path, pdf):
        out = tempfile.mkdtemp(prefix="pitato-doc-")
        try:
            os.makedirs(os.path.join(CACHE_DIR, "lo-home"), exist_ok=True)
            subprocess.run(["nice", "-n", "5", "soffice", "--headless", "--norestore",
                            "--convert-to", "pdf", "--outdir", out, path],
                           timeout=600, capture_output=True,
                           env=dict(os.environ, HOME=os.path.join(CACHE_DIR, "lo-home")))
            made = glob.glob(os.path.join(out, "*.pdf"))
            if made:
                os.makedirs(os.path.dirname(pdf), exist_ok=True)
                shutil.move(made[0], pdf)
                v["result"] = pdf
            else:
                v["result"] = "fail"
        except Exception:
            v["result"] = "fail"
        finally:
            shutil.rmtree(out, ignore_errors=True)

    # text
    def open_text(self, path, text=None):
        if text is None:
            try:
                with open(path, "rb") as f:
                    raw = f.read(TEXT_LIMIT)
                text = raw.decode("utf-8", errors="replace")
                if len(raw) == TEXT_LIMIT:
                    text += "\n\n[ file continues; only the first 2 MB is shown ]"
            except OSError:
                self.toast("Can't read that file")
                return
        self.close_viewer()
        self.v = {"type": "text", "title": os.path.basename(path), "text": text,
                  "size": 0, "lines": None, "top": 0}
        self.view = "text"
        self.dirty = True

    def text_lines(self):
        v = self.v
        if v["lines"] is None:
            font = self.fonts["mono_s" if v["size"] == 0 else "mono_l"]
            cols = max(int((self.fb.w - 40) / font.getlength("M")), 10)
            lines = []
            for raw in v["text"].expandtabs(4).splitlines():
                lines += textwrap.wrap(raw, cols, drop_whitespace=False,
                                       replace_whitespace=False) or [""]
                if len(lines) > 40000:
                    lines.append("[ too long to show the rest ]")
                    break
            v["lines"] = lines
        return v["lines"]

    def text_rows(self):
        lh = 20 if self.v.get("size", 0) == 0 else 26
        return max((self.fb.h - self.FOOTER - self.LIST_TOP) // lh, 1), lh

    PDF_ZOOMS = (1.0, 1.5, 2.0, 3.0)      # times the screen width

    def pdf_zoom(self, step):
        """X/Y: whole page, fit width, then closer — keeping the middle of the view."""
        v = self.v
        W, AH = self.fb.w, self.fb.h - self.FOOTER
        if v["fit"] == "page":
            if step > 0:
                v.update(fit="width", zoom=1.0, scroll=0, sx=0)
            return
        zs = self.PDF_ZOOMS
        i = zs.index(v["zoom"]) if v["zoom"] in zs else 0
        if step < 0 and i == 0:
            v.update(fit="page", zoom=1.0, scroll=0, sx=0)
            return
        j = max(0, min(i + step, len(zs) - 1))
        if j == i:
            self.toast("That's as close as it goes" if step > 0 else "", 2)
            return
        old = self.pdf_image()
        cx = v["sx"] + min(W, old.width) / 2 if old else W / 2
        cy = v["scroll"] + AH / 2
        r = zs[j] / zs[i]
        if (v["page"], "width", zs[j]) not in v["cache"]:
            self.render_wait(v["title"], f"Zoom {int(zs[j] * 100)}%")
        v["zoom"] = zs[j]
        v["sx"] = max(0, cx * r - W / 2)
        v["scroll"] = max(0, cy * r - AH / 2)

    def press_pdf(self, name, repeat):
        v = self.v
        W, AH = self.fb.w, self.fb.h - self.FOOTER
        if name == "b":
            self.close_viewer()
            return None
        im = self.pdf_image()
        wide = v["fit"] == "width" and im is not None and im.width > W
        if name in ("x", "y"):
            if not repeat:
                self.pdf_zoom(1 if name == "x" else -1)
        elif name in ("left", "right"):
            if wide:                                   # zoomed in: slide across the page
                v["sx"] = max(0, min(v["sx"] + (W // 3) * (1 if name == "right" else -1),
                                     im.width - W))
            elif not repeat:
                self.pdf_goto(v["page"] + (1 if name == "right" else -1))
        elif name in ("l", "r"):
            if not repeat:
                self.pdf_goto(v["page"] + (1 if name == "r" else -1))
        elif name in ("start", "select"):
            if not repeat:
                self.pdf_goto(v["page"] + (10 if name == "start" else -10))
        elif name == "a" and not repeat:
            if v["fit"] == "width":
                v.update(fit="page", zoom=1.0, scroll=0, sx=0)
            else:
                v.update(fit="width", zoom=1.0, scroll=0, sx=0)
        elif name in ("up", "down"):
            limit = max((im.height if im else AH) - AH, 0)
            step = AH // 4 * (1 if name == "down" else -1)
            if v["fit"] == "page" or limit == 0:
                if not repeat:
                    self.pdf_goto(v["page"] + (1 if name == "down" else -1))
            elif name == "down" and v["scroll"] >= limit:
                if not repeat:
                    self.pdf_goto(v["page"] + 1)
            elif name == "up" and v["scroll"] <= 0:
                if not repeat and v["page"] > 1:
                    self.pdf_goto(v["page"] - 1, at_bottom=True)
            else:
                v["scroll"] = max(0, min(v["scroll"] + step, limit))
        self.dirty = True
        return None

    def press_text(self, name, repeat):
        v = self.v
        rows, _ = self.text_rows()
        n = len(self.text_lines())
        if name == "b":
            self.close_viewer()
            return None
        if name in ("up", "down"):
            v["top"] += 1 if name == "down" else -1
        elif name in ("left", "right"):
            v["top"] += (rows - 1) * (1 if name == "right" else -1)
        elif name in ("l", "r") and not repeat:
            v["top"] = 0 if name == "l" else n
        elif name == "a" and not repeat:
            first = v["lines"][v["top"]] if v["lines"] and v["top"] < len(v["lines"]) else ""
            v["size"] = 1 - v["size"]
            v["lines"] = None
            lines = self.text_lines()
            v["top"] = next((k for k, l in enumerate(lines) if first and l.startswith(first[:20])), 0)
            rows, _ = self.text_rows()
            n = len(lines)
        v["top"] = max(0, min(v["top"], max(n - rows, 0)))
        self.dirty = True
        return None

    def render_pdf(self):
        F = self.fonts
        v = self.v
        img, d = self.canvas(PHOTO_BG)
        W, H = self.fb.w, self.fb.h
        AH = H - self.FOOTER
        im = self.pdf_image()
        wide = False
        if im is None:
            d.text((W / 2, AH / 2), "Can't show this page", font=F["big"], fill=TEXT, anchor="mm")
        elif v["fit"] == "width":
            limit = max(im.height - AH, 0)
            v["scroll"] = int(max(0, min(v["scroll"], limit)))
            wide = im.width > W
            v["sx"] = int(max(0, min(v["sx"], im.width - W))) if wide else 0
            x0 = v["sx"] if wide else 0
            part = im.crop((x0, v["scroll"], x0 + min(W, im.width), v["scroll"] + min(AH, im.height)))
            img.paste(part, ((W - part.width) // 2, 0))
            if limit:      # thin position bar on the right
                th = max(AH * AH / im.height, 20)
                ty = (AH - th) * v["scroll"] / limit
                d.rounded_rectangle((W - 6, ty, W - 2, ty + th), radius=2, fill=MUTED)
            if wide:       # and one along the bottom when the page is wider than the screen
                tw = max(W * W / im.width, 20)
                tx = (W - tw) * v["sx"] / (im.width - W)
                d.rounded_rectangle((tx, AH - 6, tx + tw, AH - 2), radius=2, fill=MUTED)
        else:
            img.paste(im, ((W - im.width) // 2, (AH - im.height) // 2))
        pg = f"{v['page']} / {v['pages']}"
        if v["fit"] == "width" and v["zoom"] != 1.0:
            pg += f"   {int(v['zoom'] * 100)}%"
        pw = d.textlength(pg, font=F["small"]) + 24
        d.rounded_rectangle((W - 12 - pw, 12, W - 12, 40), radius=14, fill=BG)
        d.text((W - 12 - pw / 2, 26), pg, font=F["small"], fill=BODY, anchor="mm")
        page_fit = ("A", "Whole page" if v["fit"] == "width" else "Fit width")
        if wide:
            hints = [("PAD", "Move"), ("X Y", "Zoom"), ("L R", "Page"), page_fit, ("B", "Back")]
        else:
            hints = [("▲▼", "Scroll"), ("◀▶", "Page"), ("X Y", "Zoom"), page_fit, ("B", "Back")]
        self.footer(d, hints)
        self.fb.show(img)

    def render_text(self):
        F = self.fonts
        v = self.v
        img, d = self.canvas()
        lines = self.text_lines()
        rows, lh = self.text_rows()
        n = len(lines)
        v["top"] = max(0, min(v["top"], max(n - rows, 0)))
        pct = 100 if n <= rows else int(100 * (v["top"] + rows) / n)
        self.title_row(d, v["title"], f"{pct}%")
        font = F["mono_s" if v["size"] == 0 else "mono_l"]
        for r in range(rows):
            k = v["top"] + r
            if k >= n:
                break
            d.text((20, self.LIST_TOP + 2 + r * lh), lines[k], font=font, fill=BODY)
        self.scrollbar(d, v["top"], rows, n, self.LIST_TOP + 4, self.LIST_TOP + rows * lh)
        self.footer(d, [("▲▼", "Scroll"), ("◀▶", "Page"),
                        ("A", "Bigger text" if v["size"] == 0 else "Smaller text"),
                        ("L R", "Start/end"), ("B", "Back")])
        self.fb.show(img)
