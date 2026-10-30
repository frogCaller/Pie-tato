"""Web, in the Home tab: Pietato's own browser (pitato/www.py fetches and reads the pages). Its first page: search, an
address, your bookmarks, the pages you've been to and sites made for browsers like it (and on a Pi 4 or 5 with
Chromium, the whole web: pitato/chromium.py). A page: its words and pictures laid out for the screen (turned with it, as
the rest is), and its links, boxes and buttons one after another: ▲▼ from one to the next (the page scrolls along), ◀▶
a screenful, A opens, B back, START an address or a search, Y a bookmark, SELECT Reader (the article on its own)."""
import bisect
import re
import threading
import time

from ..theme import ACCENT, BG, BODY, LINE, MUTED, ROW, TEXT
from ..util import item
from ..screen import slow_pi
from ..www import address, clean_title, host, picture, search_url, SITES, submit, unwrap

WWW_RECENT = 30          # pages kept in the list of where you've been
WWW_MARKS = 60           # bookmarks, at most
WWW_KEEP = 6             # pages kept to go back to without fetching them again
WWW_GAP = {"h1": 18, "h2": 14, "h3": 10, "p": 10, "li": 3, "quote": 8, "pre": 8, "small": 4}   # space over a block
WWW_INDENT = 18          # a list's (or a quote's) step in from the left
WWW_SIDE = 20            # the page's edges
WWW_LEADING = 1.4        # a line's height, its font's size times this
WWW_PICS = 2             # pictures fetched at once
WWW_PIXELS = (4 << 20, 16 << 20)   # pictures' pixels kept, at most: a Pi Zero's, a Pi 4's
WWW_PIC_MOST = 0.9       # a picture's height, at most, the page's on the screen times this
WWW_BOX_H = 40           # a form's box or button
WWW_UNDERLINE = (58, 92, 124)   # a link's line under it (its colour, dimmed)


class WwwScreen:
    """Web: its first page (a list), and a page, laid out and worked with the controller."""

    # -- its first page: a list --------------------------------------------------------------------------------------
    def www_marks(self):
        return self.state.setdefault("www", {}).setdefault("marks", [])

    def www_recent(self):
        return self.state.setdefault("www", {}).setdefault("recent", [])

    def www_rows(self):
        """Back to the page you were on (if there's one: on a Pi 4 or 5 with Chromium, it in Chromium too), Search,
        an address, Chromium, your bookmarks, where you've been (newest first), and sites made for browsers like
        this."""
        rows = []
        v = getattr(self, "www", None)
        chrome = self.chromium_here()
        if v is not None:
            rows.append(dict(item("www:page", clean_title(v["page"]), "wwwpage", v["page"].url, sub="Back to it"),
                             icon="PAGE"))
            if chrome:
                rows.append(dict(item("www:chromium:page", "This page, in Chromium", "wwwchromium", v["page"].url,
                                      sub=host(v["page"].url)), icon="FULL"))
        rows += [dict(item("www:search", "Search the web", "wwwsearch", "", sub="DuckDuckGo"), icon="FIND"),
                 dict(item("www:type", "Go to an address", "wwwtype", "", sub="Like en.wikipedia.org"), icon="GO")]
        if chrome and self.chromium_up():
            rows.append(dict(item("www:chromium", "Back to Chromium", "wwwchromium", "", sub="It's open"),
                             icon="FULL"))
        elif chrome:
            rows.append(dict(item("www:chromium", "The whole web, in Chromium", "wwwchromium", "",
                                  sub="Pages as they are"), icon="FULL"))
        seen = set()
        for m in self.www_marks():
            seen.add(m["url"])
            rows.append(dict(item("www:mark:" + m["url"], m["title"], "wwwgo", m["url"], sub=host(m["url"])),
                             icon="MARK"))
        for r in self.www_recent():
            if r["url"] not in seen:
                seen.add(r["url"])
                rows.append(dict(item("www:past:" + r["url"], r["title"], "wwwgo", r["url"], sub=host(r["url"])),
                                 icon="PAST"))
        for name, url in SITES:
            if url not in seen:
                rows.append(dict(item("www:site:" + url, name, "wwwgo", url, sub=host(url)), icon="SITE"))
        return rows

    def www_open_row(self, it):
        """A on a row of its first page."""
        kind = it["kind"]
        if kind == "wwwpage":
            self.www_shown = True
            self.dirty = True
        elif kind == "wwwsearch":
            self.open_keyboard("Search the web", "", lambda q: self.www_go(search_url(q)), limit=120, local=True)
        elif kind == "wwwtype":
            self.open_keyboard("Address", "", lambda text: self.www_go(address(text)), limit=200, local=True)
        elif kind == "wwwchromium":
            self.chromium_open(it.get("src") or None)
        elif kind == "wwwgo":
            self.www_go(it["src"])

    def www_forget(self, it):
        """Y on a bookmark, or a page you've been to: off the list. On Chromium, while it's open: closed."""
        key = it.get("key", "")
        st = self.state.setdefault("www", {})
        if key.startswith("www:mark:"):
            st["marks"] = [m for m in self.www_marks() if m["url"] != it["src"]]
            self.toast("Bookmark removed", 2)
        elif key.startswith("www:past:"):
            st["recent"] = [r for r in self.www_recent() if r["url"] != it["src"]]
            self.toast("Taken off the list", 2)
        elif key == "www:chromium" and self.chromium_up():
            self.chromium_close()                      # (it's open: closed)
            self.toast("Chromium closed", 2)
            return
        else:
            return
        self.save_state()
        self.www_list_again()

    def www_list_again(self, keep=None):
        """Its first page's rows afresh, the one you were on still picked (or `keep`'s)."""
        i = self.tab_index("www")
        if i is None:
            return
        rows = self.tab_items(i)
        sel = self.sels.get(i, 0)
        was = keep or (rows[sel]["key"] if rows and 0 <= sel < len(rows) else None)
        self.items[i] = self.www_rows()
        keys = [r["key"] for r in self.items[i]]
        self.sels[i] = keys.index(was) if was in keys else min(sel, max(len(keys) - 1, 0))
        self.dirty = True

    def www_on_page(self):
        """A page is on the screen (not its first page)."""
        return getattr(self, "www", None) is not None and getattr(self, "www_shown", False)

    # -- going to a page --------------------------------------------------------------------------------------------
    def www_go(self, url, data=None, keep=True):
        """A page fetched (on a thread of its own: the screen says it's loading, and B gives up on it)."""
        if not url:
            return
        url = unwrap(url)
        v = getattr(self, "www", None)
        referer = v["page"].url if v is not None else None
        self.www_wait = {"url": url, "host": host(url) or url, "keep": keep, "since": time.monotonic()}
        self.www_loader.on_done = lambda page, error: self.soon(lambda: self.www_arrived(page, error))
        self.www_loader.load(url, data=data, referer=referer)
        self.dirty = True

    def www_arrived(self, page, error):
        wait, self.www_wait = getattr(self, "www_wait", None), None
        if wait is None:                               # (given up on: B)
            return
        self.dirty = True
        if page is None:
            self.toast(error or "Couldn't show that page", 4)
            return
        if page.kind == "pdf":
            self.www_pdf(page)
            return
        v = getattr(self, "www", None)
        if v is not None and wait["keep"]:
            self.www_back.append({"page": v["page"], "url": v["page"].url, "y": v["y"], "focus": v["focus"],
                                  "reader": v["reader"]})
            for old in self.www_back[:-WWW_KEEP]:     # (older ones: fetched again, if it comes to that)
                old["page"] = None
        self.www = {"page": page, "y": 0, "focus": None, "reader": False, "laid": None, "lines": [], "targets": [],
                    "height": 0}
        self.www_shown = True
        self.www_seen(page)
        self.www_list_again(keep="www:page")

    def www_seen(self, page):
        """A page you've been to, first on the list of them (not a picture or a search's results)."""
        if page.kind != "html" or "duckduckgo.com" in host(page.url):
            return
        recent = [r for r in self.www_recent() if r["url"] != page.url]
        recent.insert(0, {"url": page.url, "title": clean_title(page)[:120]})
        self.state.setdefault("www", {})["recent"] = recent[:WWW_RECENT]
        self.save_state()

    def www_pdf(self, page):
        """A PDF: kept in Documents and opened, as the Files tab would."""
        import os
        from ..config import home_dir
        name = re.sub(r"[^\w .()-]", "_", page.url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "page.pdf")
        name = name if name.lower().endswith(".pdf") else name + ".pdf"
        folder = os.path.join(home_dir(), "Documents")
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, name)
            with open(path, "wb") as f:
                f.write(page.data)
            st = os.stat(folder)
            os.chown(path, st.st_uid, st.st_gid)
        except OSError:
            self.toast("Couldn't keep that PDF", 3)
            return
        self.toast(f"Kept in Documents: {name}", 3)
        self.open_pdf(path)

    def www_close_page(self):
        """Its first page again (the page kept: Back to it, at the top)."""
        self.www_shown = False
        self.www_list_again(keep="www:page")

    def www_go_back(self):
        """B on a page: the page before (or, before the first, its first page)."""
        if getattr(self, "www_wait", None) is not None:
            self.www_wait = None                       # (given up on)
            self.www_loader.n += 1
            self.dirty = True
            return
        if not self.www_back:
            self.www_close_page()
            return
        old = self.www_back.pop()
        if old.get("page") is None:
            self.www_go(old["url"], keep=False)
            return
        self.www = {"page": old["page"], "y": old["y"], "focus": old["focus"], "reader": old["reader"],
                    "laid": None, "lines": [], "targets": [], "height": 0}
        self.dirty = True

    # -- laying a page out ------------------------------------------------------------------------------------------
    def www_area(self):
        """(top, bottom) of the page on the screen: under the line saying where you are, over the buttons."""
        return self.list_top(), self.fb.h - self.FOOTER

    def www_fonts(self):
        F = self.fonts
        return {"p": F["www"], "b": F["www_b"], "h1": F["www_h1"], "h2": F["www_h2"], "h3": F["www_h3"],
                "small": F["small"], "small_b": F["small_b"], "pre": F["mono_s"]}

    def www_blocks(self):
        v = self.www
        return v["page"].reader if v["reader"] and v["page"].reader else v["page"].blocks

    def www_layout(self):
        """The page's lines and what can be picked on them (links, boxes, buttons), for the screen as it is (laid out
        again when it's turned, Reader's on or off, or a picture comes); what was at the top of the screen kept
        there."""
        v = self.www
        top, bottom = self.www_area()
        key = (self.fb.w, bottom - top, v["reader"])
        if v["laid"] == key:
            return
        anchor = None
        if v["lines"]:
            first = next((ln for ln in v["lines"] if ln["y"] + ln["h"] > v["y"]), None)
            if first is not None:
                anchor = (first["block"], v["y"] - first["y"])
        fresh = not v["targets"]                       # (a page put back: where you were, and what you'd picked, kept)
        focus_ref = v["targets"][v["focus"]]["ref"] if not fresh and v["focus"] is not None \
            and v["focus"] < len(v["targets"]) else None
        v["lines"], v["targets"], v["height"] = self.www_lay(self.www_blocks(), self.fb.w, bottom - top)
        v["ends"] = [ln["y"] + ln["h"] for ln in v["lines"]]     # (where each line ends: the first on the screen
        v["pic_lines"] = [k for k, ln in enumerate(v["lines"]) if "img" in ln]   # found quickly, and the pictures)
        v["laid"] = key
        if anchor is not None:
            ln = next((x for x in v["lines"] if x["block"] >= anchor[0]), None)
            v["y"] = ln["y"] + anchor[1] if ln is not None else v["y"]
        if fresh:
            v["focus"] = v["focus"] if v["focus"] is not None and v["focus"] < len(v["targets"]) else None
        else:
            v["focus"] = next((k for k, t in enumerate(v["targets"]) if t["ref"] == focus_ref), None) \
                if focus_ref is not None else None
        self.www_clamp()

    def www_lay(self, blocks, width, view_h):
        """(lines, targets, height): each line {y, h, block, items: [(x, text, font, role, target)], and a picture
        (img), a box (box) or a rule}; each target {kind: link, field or button, ref, boxes: [(line, x0, x1)], y0,
        y1}."""
        fonts = self.www_fonts()
        page = self.www["page"]
        left, right = WWW_SIDE, width - WWW_SIDE - 8   # (room for the scrollbar)
        lines, targets = [], []
        y = 6
        state = {"link": None}                         # the link last laid out (one spanning blocks is one target)
        widths = {}

        def w_of(text, fk):
            k = (text, fk)
            if k not in widths:
                widths[k] = fonts[fk].getlength(text)
            return widths[k]

        def target(kind, ref, li, x0, x1, extra=None):
            t = targets[-1] if targets else None
            if kind == "link" and t is not None and t["kind"] == "link" and t["ref"] == ("link", ref) \
                    and state["link"] == ref:
                t["boxes"].append((li, x0, x1))
                t["y1"] = max(t["y1"], lines[li]["y"] + lines[li]["h"])
                return len(targets) - 1
            targets.append({"kind": kind, "ref": (kind, ref), "boxes": [(li, x0, x1)], "y0": lines[li]["y"],
                            "y1": lines[li]["y"] + lines[li]["h"], "b": extra})
            return len(targets) - 1

        for bi, b in enumerate(blocks):
            kind = b["kind"]
            if kind == "text":
                y = self.www_lay_text(b, bi, y, lines, target, state, fonts, w_of, left, right)
            elif kind == "image":
                im = page.images[b["img"]]
                y += 6
                w, h = self.www_pic_size(im, right - left, view_h)
                lines.append({"y": y, "h": h, "block": bi, "items": [], "img": (b["img"], left, w, h)})
                if b.get("link") is not None:
                    t = target("link", b["link"], len(lines) - 1, left, left + w)
                    lines[-1]["img"] += (t,)
                    state["link"] = b["link"]
                else:
                    lines[-1]["img"] += (None,)
                    state["link"] = None
                y += h + 6
            elif kind in ("field", "button"):
                y += 8
                label = b["label"] if kind == "button" else (b.get("value") or b["label"])
                fk = "b" if kind == "button" else "p"
                bw = min(right - left, max(160, int(w_of(label[:80], fk)) + 40)) if kind == "button" \
                    else min(right - left, 520)
                lines.append({"y": y, "h": WWW_BOX_H, "block": bi, "items": [], "box": [kind, left, left + bw, label]})
                t = target(kind, id(b), len(lines) - 1, left, left + bw, extra=b)
                lines[-1]["box"].append(t)
                state["link"] = None
                y += WWW_BOX_H + 6
            elif kind == "rule":
                y += 10
                lines.append({"y": y, "h": 2, "block": bi, "items": [], "rule": True})
                y += 12
        return lines, targets, y + 24

    def www_lay_text(self, b, bi, y, lines, target, state, fonts, w_of, left, right):
        """A block of text into lines: word by word, as many on a line as fit (a word too long for one, an address,
        broken where it must be)."""
        style = b["style"]
        base = {"h1": "h1", "h2": "h2", "h3": "h3", "small": "small", "pre": "pre"}.get(style, "p")
        lh = int(fonts[base].size * WWW_LEADING)
        y += WWW_GAP.get(style, 8) if lines else 0
        x0 = left + min(b.get("indent", 0), 6) * WWW_INDENT
        if style == "quote":
            x0 += 6
        line = {"y": y, "h": lh, "block": bi, "items": [], "quote": style == "quote"}
        lines.append(line)
        x = x0
        space = False

        def newline():
            nonlocal line, x, y
            y += lh
            line = {"y": y, "h": lh, "block": bi, "items": [], "quote": style == "quote"}
            lines.append(line)
            x = x0

        def place(text, fk, role, link):
            nonlocal x
            w = w_of(text, fk)
            t = None
            if link is not None:
                t = target("link", link, len(lines) - 1, x, x + w)
            last = line["items"][-1] if line["items"] else None
            if last is not None and last[2:5] == (fk, role, t) and abs(last[0] + last[5] - x) < 0.5:
                line["items"][-1] = (last[0], last[1] + text, fk, role, t, last[5] + w)
            else:
                line["items"].append((x, text, fk, role, t, w))
            x += w
            state["link"] = link

        for text, link, bold in b["runs"]:
            fk = base if not bold else {"p": "b", "small": "small_b"}.get(base, base)
            role = "link" if link is not None else "head" if base in ("h1", "h2", "h3") else \
                "muted" if base == "small" else "body"
            parts = re.split(r"(\n)", text) if style == "pre" else re.split(r"(\n| +)", text)
            for part in parts:
                if not part:
                    continue
                if part == "\n":
                    if line["items"] or style == "pre":
                        newline()
                    space = False
                    continue
                if part.isspace() and style != "pre":
                    space = True
                    continue
                gap = (w_of(" ", fk) if space and x > x0 else 0)
                w = w_of(part, fk)
                if x + gap + w > right and x > x0:
                    newline()
                    gap = 0
                while w > right - x and len(part) > 1:          # (too long for what's left of a line: broken)
                    cut = max(1, int(len(part) * (right - x - gap) / w))
                    while cut > 1 and w_of(part[:cut], fk) > right - x - gap:
                        cut -= 1
                    if gap:
                        place(" ", fk, role, link)
                        gap = 0
                    place(part[:cut], fk, role, link)
                    newline()
                    part = part[cut:]
                    w = w_of(part, fk)
                if gap:
                    place(" ", fk, role, link if state["link"] == link else None)
                place(part, fk, role, link)
                space = False
            if link is None:
                state["link"] = None
        if not line["items"]:
            lines.pop()
            y -= lh
        return y + lh

    def www_pic_size(self, im, room, view_h):
        """(width, height) a picture takes on the page: as it came (made smaller to fit), or, till it comes, as its
        page says it is (or a box)."""
        pic = self.www_pic(im)
        if pic:
            return pic.size
        most_h = int(view_h * WWW_PIC_MOST)
        w, h = im.get("w") or 0, im.get("h") or 0
        if w and h:
            k = min(1.0, room / w, most_h / h)
            return max(int(w * k), 24), max(int(h * k), 24)
        return min(room, 220), 120

    # -- pictures: fetched as they're near the screen ---------------------------------------------------------------
    def www_pic(self, im):
        """A page's picture, ready to draw (made smaller to fit), or None (not yet, or it can't be had: False)."""
        return self.www_pics.get(im["src"])

    def www_want_pics(self):
        """The pictures a screenful either side of the one on the screen: asked for, if they aren't yet."""
        v = self.www
        top, bottom = self.www_area()
        vh = bottom - top
        lo, hi = v["y"] - vh, v["y"] + 2 * vh
        page = v["page"]
        room = self.fb.w - 2 * WWW_SIDE - 8
        for k in v.get("pic_lines", ()):
            ln = v["lines"][k]
            if lo <= ln["y"] + ln["h"] and ln["y"] <= hi:
                im = page.images[ln["img"][0]]
                src = im["src"]
                if src in self.www_pics or src in self.www_pic_asked:
                    continue
                self.www_pic_asked.add(src)
                self.www_pic_queue.append((src, im.get("data"), room, int(vh * WWW_PIC_MOST)))
        while self.www_pic_queue and self.www_pic_threads < WWW_PICS:
            self.www_pic_threads += 1
            threading.Thread(target=self.www_pic_job, daemon=True).start()

    def www_pic_job(self):
        while True:
            with self.www_pic_lock:
                if not self.www_pic_queue:
                    self.www_pic_threads -= 1
                    return
                src, data, room, most_h = self.www_pic_queue.popleft()
            pic = picture(src, data)
            if pic is not None:
                k = min(1.0, room / pic.width, most_h / pic.height)
                if k < 1.0:
                    from PIL import Image
                    pic = pic.resize((max(1, int(pic.width * k)), max(1, int(pic.height * k))), Image.BILINEAR)
            self.soon(lambda src=src, pic=pic: self.www_pic_came(src, pic))

    def www_pic_came(self, src, pic):
        """A picture come (or not: False): the page laid out again if it's another size than the room left for it."""
        self.www_pic_asked.discard(src)
        self.www_pics[src] = pic if pic is not None else False
        self.www_pics.move_to_end(src)
        v = self.www
        if v is not None and pic is not None:
            for k in v.get("pic_lines", ()):
                i, _, w, h, _ = v["lines"][k]["img"]
                if v["page"].images[i]["src"] == src and (abs(pic.width - w) > 1 or abs(pic.height - h) > 1):
                    v["laid"] = None
        most = WWW_PIXELS[0] if slow_pi() else WWW_PIXELS[1]
        total = sum(p.width * p.height for p in self.www_pics.values() if p)
        while total > most and len(self.www_pics) > 1:       # (the oldest go: fetched again if they're wanted)
            old_src, old = self.www_pics.popitem(last=False)
            if old:
                total -= old.width * old.height
        if self.www_on_page() and self.view == "list" and self.tab_type() == "www":
            self.dirty = True

    # -- moving about a page ------------------------------------------------------------------------------------------
    def www_clamp(self):
        v = self.www
        top, bottom = self.www_area()
        v["y"] = max(0, min(v["y"], max(0, v["height"] - (bottom - top))))

    def www_in_view(self, t):
        v = self.www
        top, bottom = self.www_area()
        return t["y0"] >= v["y"] and t["y1"] <= v["y"] + (bottom - top)

    def www_step(self, d):
        """▲▼: on to the next link, box or button (or the one before), if it's on the screen; the page scrolled a third
        of a screen, if it isn't (and then on to it, if that brought it on)."""
        v = self.www
        top, bottom = self.www_area()
        vh = bottom - top
        ts = v["targets"]
        f = v["focus"]
        if d > 0:
            nxt = next((k for k in range((f + 1) if f is not None else 0, len(ts)) if ts[k]["y0"] >= v["y"]), None)
        else:
            nxt = next((k for k in range((f - 1) if f is not None else len(ts) - 1, -1, -1)
                        if ts[k]["y1"] <= v["y"] + vh), None)
        if nxt is not None and self.www_in_view(ts[nxt]):
            v["focus"] = nxt
            return
        v["y"] += d * max(vh // 3, 40)
        self.www_clamp()
        if nxt is not None and self.www_in_view(ts[nxt]):
            v["focus"] = nxt
        elif f is not None and not self.www_in_view(ts[f]):
            v["focus"] = None

    def www_page(self, d):
        """◀▶: a screenful back or on (a line kept from the one before), the first link on it picked."""
        v = self.www
        top, bottom = self.www_area()
        lh = int(self.fonts["www"].size * WWW_LEADING)
        v["y"] += d * max(bottom - top - 2 * lh, 40)
        self.www_clamp()
        on = [k for k, t in enumerate(v["targets"]) if self.www_in_view(t)]
        v["focus"] = on[0] if on else None

    def www_activate(self):
        """A: the link opened, a box typed in, a button pressed (its form sent)."""
        v = self.www
        if v["focus"] is None or v["focus"] >= len(v["targets"]):
            return
        t = v["targets"][v["focus"]]
        page = v["page"]
        if t["kind"] == "link":
            self.www_go(page.links[t["ref"][1]])
        elif t["kind"] == "field":
            b = t["b"]
            self.open_keyboard(b["label"][:40] or "Type here", b.get("value", ""),
                               lambda text, b=b: self.www_typed(b, text), empty=True, limit=200, local=True)
        elif t["kind"] == "button":
            b = t["b"]
            extra = [(b["name"], b.get("value", ""))] if b.get("name") else []
            url, data = submit(page, b["form"], extra)
            self.www_go(url, data=data)

    def www_typed(self, b, text):
        """What you typed in a page's box: in it; and its form sent, if it's the form's only box (a search)."""
        b["value"] = text
        self.www["laid"] = None
        page = self.www["page"]
        boxes = [x for x in page.blocks if x["kind"] == "field" and x["form"] == b["form"]]
        if len(boxes) == 1 and text.strip():
            url, data = submit(page, b["form"])
            self.www_go(url, data=data)
        self.dirty = True

    def www_mark(self):
        """Y on a page: a bookmark (or, if it's one, not any more)."""
        page = self.www["page"]
        marks = self.www_marks()
        if any(m["url"] == page.url for m in marks):
            self.state["www"]["marks"] = [m for m in marks if m["url"] != page.url]
            self.toast("Bookmark removed", 2)
        else:
            marks.insert(0, {"url": page.url, "title": clean_title(page)[:120]})
            del marks[WWW_MARKS:]
            self.toast("Bookmarked: it's on Web's first page", 3)
        self.save_state()
        self.www_list_again()

    def www_reader(self):
        """SELECT: Reader (the page's article on its own), or the whole page again."""
        v = self.www
        if not v["page"].reader:
            self.toast("Reader: this page has no article to read on its own", 3)
            return
        v["reader"] = not v["reader"]
        v["laid"], v["lines"], v["targets"], v["y"], v["focus"] = None, [], [], 0, None
        self.toast("Reader: just the article" if v["reader"] else "The whole page", 2)

    def press_www(self, name, repeat):
        """The buttons on a page (and its first page's Y and START); 'pass' for the rest (L R, X, a list's)."""
        if not self.www_on_page():
            if name == "b" and getattr(self, "www_wait", None) is not None:
                if not repeat:
                    self.www_go_back()                 # (loading: given up on)
                return None
            if name == "start" and not repeat:
                self.www_open_row({"kind": "wwwsearch"})
                return None
            if name == "y" and not repeat:
                items = self.tab_items()
                sel = self.sels.get(self.tab, 0)
                if items and 0 <= sel < len(items):
                    self.www_forget(items[sel])
                return None
            return "pass"
        if name in ("l", "r", "x"):
            return "pass"
        self.www_layout()                              # (as it is on the screen now: the screen may have turned)
        if name == "b":
            if not repeat:
                self.www_go_back()
        elif getattr(self, "www_wait", None) is not None:
            return None                                # (loading: only B, to give up on it)
        elif name in ("up", "down"):
            self.www_step(1 if name == "down" else -1)
        elif name in ("left", "right"):
            self.www_page(1 if name == "right" else -1)
        elif name == "a" and not repeat:
            self.www_activate()
        elif name == "start" and not repeat:
            self.open_keyboard("Search, or an address", "", lambda text: self.www_go(address(text)), limit=200,
                               local=True)
        elif name == "y" and not repeat:
            self.www_mark()
        elif name == "select" and not repeat:
            self.www_reader()
        self.dirty = True
        return None

    # -- drawing ------------------------------------------------------------------------------------------------------
    def www_hints(self):
        v = self.www
        if getattr(self, "www_wait", None) is not None:
            return [("B", "Stop")]
        t = v["targets"][v["focus"]] if v["focus"] is not None and v["focus"] < len(v["targets"]) else None
        first = ("A", {"link": "Open", "field": "Type", "button": "Send"}[t["kind"]]) if t else None
        return ([first] if first else []) + [("▲▼", "Links"), ("◀▶", "Page"), ("START", "Go to"), ("B", "Back")]

    def render_www(self):
        """A page: what's on the screen of it, the link, box or button picked lit up; where you are along the top."""
        from PIL import Image, ImageDraw
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        self.header(img, d)
        v = self.www
        self.www_layout()
        self.www_want_pics()
        top, bottom = self.www_area()
        vh = bottom - top
        page = v["page"]
        wait = getattr(self, "www_wait", None)
        right = f"Loading {wait['host']}…" if wait else ("Reader" if v["reader"] else host(page.url))
        rw = d.textlength(right, font=F["small"]) + 16 if right else 0
        d.text((W - 20, self.LIST_TOP + 10), right, font=F["small"], fill=ACCENT if wait or v["reader"] else MUTED,
               anchor="rm")
        d.text((20, self.LIST_TOP + 10), self.fit(d, "Web  ›  " + clean_title(page), F["small"], W - 40 - rw),
               font=F["small"], fill=MUTED, anchor="lm")
        sheet = Image.new("RGB", (W, max(vh, 1)), BG)
        sd = ImageDraw.Draw(sheet)
        fonts = self.www_fonts()
        colours = {"body": BODY, "head": TEXT, "muted": MUTED, "link": ACCENT}
        y0 = v["y"]
        focus = v["focus"]
        first = bisect.bisect_right(v.get("ends", []), y0)     # (the first line that's on the screen)
        if focus is not None and focus < len(v["targets"]):    # the one picked: lit up behind it
            for li, x0, x1 in v["targets"][focus]["boxes"]:
                ln = v["lines"][li]
                if "img" not in ln and "box" not in ln:
                    sd.rounded_rectangle((x0 - 4, ln["y"] - y0, x1 + 4, ln["y"] + ln["h"] - y0), radius=6, fill=ROW)
        for ln in v["lines"][first:]:
            ly = ln["y"] - y0
            if ly > vh:
                break
            if ln.get("quote"):
                sd.rectangle((WWW_SIDE, ly, WWW_SIDE + 2, ly + ln["h"]), fill=LINE)
            if ln.get("rule"):
                sd.line((WWW_SIDE, ly, W - WWW_SIDE, ly), fill=LINE, width=1)
            for x, text, fk, role, t, w in ln["items"]:
                lit = t is not None and t == focus
                mid = ly + ln["h"] / 2
                sd.text((x, mid), text, font=fonts[fk], fill=TEXT if lit else colours[role], anchor="lm")
                if t is not None and not lit:          # (a link: underlined, so two side by side are two)
                    uy = mid + fonts[fk].size * 0.62
                    sd.line((x, uy, x + w, uy), fill=WWW_UNDERLINE, width=1)
            if "img" in ln:
                k, x, w, h, t = ln["img"]
                pic = self.www_pic(page.images[k])
                if pic:
                    sheet.paste(pic, (int(x), int(ly)))
                else:
                    sd.rounded_rectangle((x, ly, x + w, ly + h), radius=8, fill=ROW)
                    alt = page.images[k].get("alt") or ("Couldn't get this picture" if pic is False else "Picture")
                    sd.text((x + w / 2, ly + h / 2), self.fit(sd, alt, F["small"], w - 16), font=F["small"],
                            fill=MUTED, anchor="mm")
                if t is not None and t == focus:
                    sd.rounded_rectangle((x - 3, ly - 3, x + w + 3, ly + h + 3), radius=8, outline=ACCENT, width=3)
            if "box" in ln:
                kind, x0, x1, label, t = ln["box"]
                lit = t == focus
                if kind == "field":
                    sd.rounded_rectangle((x0, ly, x1, ly + ln["h"]), radius=8, fill=ROW,
                                         outline=ACCENT if lit else LINE, width=2)
                    typed = bool(v["targets"][t]["b"].get("value"))
                    sd.text((x0 + 14, ly + ln["h"] / 2), self.fit(sd, label, F["www"], x1 - x0 - 28), font=F["www"],
                            fill=TEXT if typed else MUTED, anchor="lm")
                else:
                    sd.rounded_rectangle((x0, ly, x1, ly + ln["h"]), radius=ln["h"] // 2,
                                         fill=ACCENT if lit else ROW)
                    sd.text(((x0 + x1) / 2, ly + ln["h"] / 2), self.fit(sd, label, F["www_b"], x1 - x0 - 24),
                            font=F["www_b"], fill=BG if lit else TEXT, anchor="mm")
        img.paste(sheet, (0, top))
        if v["height"] > vh:
            self.scrollbar(d, v["y"], vh, v["height"], top + 4, bottom - 4)
        if wait:
            label = f"Loading {wait['host']}…"
            pw = d.textlength(label, font=F["small"]) + 36
            d.rounded_rectangle(((W - pw) / 2, top + 10, (W + pw) / 2, top + 42), radius=16, fill=ROW, outline=ACCENT)
            d.text((W / 2, top + 26), label, font=F["small"], fill=TEXT, anchor="mm")
        self.footer(d, self.www_hints())
        self.fb.show(img)
