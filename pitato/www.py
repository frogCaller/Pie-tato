"""The web, as text and pictures: a page fetched (http and https, its redirects followed, its cookies kept while
Pietato runs), its HTML read into blocks (headings, paragraphs, lists, quotes, a table a row at a time, pictures,
links, and its forms' boxes and buttons), with no JavaScript run; its pictures fetched as they're wanted; searches
through DuckDuckGo's page for browsers without JavaScript. Reader picks out a page's article. (pitato/screens/www.py
draws it and works it with the controller.)"""
import gzip
import html
import http.cookiejar
import io
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

UA_WWW = "Mozilla/5.0 (X11; Linux aarch64; rv:128.0) Gecko/20100101 Firefox/128.0"   # (a browser's: sites send
                                                     # their plain pages to it, and turn away ones they don't know)
PAGE_MOST = 3 << 20          # bytes of a page read, at most
PDF_MOST = 40 << 20          # ...of a PDF (kept in Documents, and opened)
PICTURE_MOST = 6 << 20       # ...of a picture
PICTURES_MOST = 80           # pictures on a page, at most
TIMEOUT = 20                 # seconds a page or a picture has to come
SEARCH = "https://html.duckduckgo.com/html/?q={q}"   # (its page for browsers without JavaScript)
SITES = [("Wikipedia", "https://en.m.wikipedia.org/"), ("NPR, as text", "https://text.npr.org/"),
         ("CNN, lite", "https://lite.cnn.com/"), ("Hacker News", "https://news.ycombinator.com/"),
         ("Wiby, the old-style web", "https://wiby.me/")]    # (on the start page: sites made for browsers like this)
SKIP = {"script", "style", "template", "svg", "math", "iframe", "object", "embed", "canvas", "video", "audio",
        "select", "datalist", "dialog", "map", "button", "textarea", "noembed"}   # what's in these isn't shown (a
                                     # <select>: its choice is sent with its form; a <button>: its words its label)
HIDE_CLASSES = {"hidden", "sr-only", "visually-hidden", "visuallyhidden", "screen-reader-text", "d-none", "hide",
                "is-hidden", "u-hidden"}   # (words for screen readers, and what a page's own JavaScript would show)
BLOCKS = {"p", "div", "section", "article", "main", "header", "footer", "nav", "aside", "h1", "h2", "h3", "h4", "h5",
          "h6", "ul", "ol", "li", "dl", "dt", "dd", "blockquote", "pre", "table", "tr", "form", "figure",
          "figcaption", "details", "summary", "address", "fieldset", "legend", "center", "hgroup", "body", "html",
          "caption", "tbody", "thead", "tfoot", "menu", "search"}
HEADINGS = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h3", "h5": "h3", "h6": "h3"}
VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "param", "source", "track", "wbr"}
CONTAINERS = {"div", "section", "article", "main", "td", "body", "center", "blockquote"}   # (Reader looks among these)
TEXT_TYPES = {"text", "search", "email", "url", "tel", "number", "", None}   # an <input> you type in
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
SPACES = re.compile(r"[ \t\r\n\f ​]+")
META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-:.]+)""", re.I)
_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


class WebError(Exception):
    """Why a page didn't come, in words for the screen."""


def address(text):
    """What was typed in the box, as an address to go to: an address as it is (https:// put in front of one without
    it, as a browser does), anything else a search."""
    t = (text or "").strip()
    if not t:
        return None
    if re.match(r"^https?://", t, re.I):
        return t
    if " " not in t and re.match(r"^(localhost|[\w-]+(\.[\w-]+)+|\d{1,3}(\.\d{1,3}){3})(:\d+)?(/.*)?$", t):
        return "https://" + t if not re.match(r"^(localhost|\d)", t) else "http://" + t
    return search_url(t)


def search_url(words):
    """A search's address, for its words."""
    return SEARCH.format(q=urllib.parse.quote_plus((words or "").strip()))


def unwrap(url):
    """A search result's own address, not DuckDuckGo's way through to it (//duckduckgo.com/l/?uddg=...)."""
    p = urllib.parse.urlsplit(url)
    if p.netloc.endswith("duckduckgo.com") and p.path.startswith("/l/"):
        q = urllib.parse.parse_qs(p.query).get("uddg")
        if q and re.match(r"^https?://", q[0]):
            return q[0]
    return url


def host(url):
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def fetch(url, data=None, referer=None, most=PAGE_MOST, accept="text/html,*/*;q=0.8"):
    """(the address it came from, after its redirects; its kind, as its server says; its bytes, at most `most`).
    data: a form's fields, sent as a POST. WebError if it doesn't come."""
    headers = {"User-Agent": UA_WWW, "Accept": accept, "Accept-Language": "en-US,en;q=0.7",
               "Accept-Encoding": "gzip, deflate"}
    if referer:
        headers["Referer"] = referer
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with _opener.open(req, timeout=TIMEOUT) as r:
            final, kind = r.geturl(), r.headers.get("Content-Type", "")
            coding = (r.headers.get("Content-Encoding") or "").lower()
            if kind.split(";")[0].strip().lower() == "application/pdf":
                most = max(most, PDF_MOST)
            raw = r.read(most + 1)
    except urllib.error.HTTPError as ex:
        raise WebError(f"The site said {ex.code}" + (f" ({ex.reason})" if ex.reason else "")) from ex
    except urllib.error.URLError as ex:
        why = str(getattr(ex, "reason", ex))
        if "Name or service not known" in why or "getaddrinfo" in why or "Temporary failure in name" in why:
            raise WebError("Couldn't find that site. Check the address, and the WiFi") from ex
        if "CERTIFICATE" in why.upper():
            raise WebError("That site's certificate isn't right") from ex
        raise WebError("Couldn't reach that site") from ex
    except (OSError, ValueError) as ex:
        raise WebError("Couldn't reach that site") from ex
    try:
        if coding == "gzip":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(most + 1)
        elif coding == "deflate":
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                raw = zlib.decompress(raw, -15)
    except (OSError, EOFError, zlib.error) as ex:
        raise WebError("That page came garbled") from ex
    return final, kind, raw[:most]


def page_text(raw, kind):
    """A page's bytes as text: in the character set its server or its page says, else UTF-8 (or Windows' own, if
    it isn't that)."""
    m = re.search(r"charset=([\w\-:.]+)", kind or "", re.I) or META_CHARSET.search(raw[:4096])
    names = [m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)] if m else []
    for name in names + ["utf-8"]:
        try:
            return raw.decode(name)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("cp1252", errors="replace")


class Page:
    """A page, read: its address, its title, its blocks, and what they point at (links, forms, pictures)."""

    def __init__(self, url):
        self.url, self.title = url, ""
        self.blocks = []            # dicts, in order: kind text (style, runs, indent), image, field, button, rule
        self.links = []             # addresses
        self.forms = []             # {"action", "method", "fields": [(name, value)]}
        self.images = []            # {"src", "alt", "w", "h"}: their pictures fetched later (pitato/screens/www.py)
        self.reader = None          # Reader's blocks (the article), or None if it can't find one
        self.kind = "html"          # html, image (a picture on its own), text, pdf (its bytes in data)
        self.data = b""


class Reader(HTMLParser):
    """HTML into a Page's blocks."""

    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.base = page.url
        self.skip_tag, self.skip_depth = None, 0   # the element whose insides aren't shown, open now (how deep in
        self.skip_words = []                       # itself), and its words (a button's: its label)
        self.choice = None                         # a <select>'s name and its choice so far
        self.stack = []             # the open elements: (tag, its container's number or None)
        self.link = None            # the link the text's in now
        self.bold = 0
        self.pre = 0
        self.runs = []              # the block being made: [text, link, bold]
        self.style = "p"
        self.indent = 0
        self.lists = []             # open lists: [ordered?, count]
        self.form = None            # the form open now (its index)
        self.title, self.in_title = [], False
        self.cid = 0                # (containers, numbered as they open: Reader looks among them)
        self.cells = 0              # cells in the table row being made

    # -- making blocks ----------------------------------------------------------------------------------------------
    def containers(self):
        return tuple(c for _, c in self.stack if c is not None)

    def flush(self):
        """The text made so far, a block of its own (if there's any)."""
        runs = [list(r) for r in self.runs if r[0]]
        self.runs = []
        if not runs:
            return
        if self.style != "pre":
            runs[0][0] = runs[0][0].lstrip()
            runs[-1][0] = runs[-1][0].rstrip()
            runs = [r for r in runs if r[0]]
            if not runs or not "".join(r[0] for r in runs).strip():
                return
        self.page.blocks.append({"kind": "text", "style": self.style, "runs": [tuple(r) for r in runs],
                                 "indent": self.indent, "in": self.containers()})

    def add_text(self, text):
        if self.pre:
            text = text.replace("\r\n", "\n").replace("\t", "    ")
        else:
            text = SPACES.sub(" ", text)
            if not self.runs or self.runs[-1][0].endswith((" ", "\n")):
                text = text.lstrip(" ")
        if not text:
            return
        if self.runs and self.runs[-1][1] == self.link and self.runs[-1][2] == bool(self.bold):
            self.runs[-1][0] += text
        else:
            self.runs.append([text, self.link, bool(self.bold)])

    def block(self, style=None):
        self.flush()
        self.style = style or ("pre" if self.pre else "p")

    def absolute(self, url):
        url = (url or "").strip()
        if not url or url.startswith(("javascript:", "data:", "mailto:", "tel:", "#")):
            return None
        try:
            return urllib.parse.urljoin(self.base, url)
        except ValueError:
            return None

    @staticmethod
    def hidden(a):
        classes = set((a.get("class") or "").lower().split())
        return ("hidden" in a or a.get("aria-hidden") == "true" or bool(classes & HIDE_CLASSES)
                or bool(HIDDEN_STYLE.search(a.get("style") or "")))

    # -- the parser's own -------------------------------------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title" and not self.skip_tag:
            self.in_title = True
            return
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth += 1
            elif tag == "option" and self.choice is not None:
                value = a.get("value")
                if self.choice[1] is None or "selected" in a:
                    self.choice[1] = value if value is not None else ""
                    self.choice[2] = value is None     # (no value: its words are)
            return
        if tag == "base" and a.get("href"):
            self.base = urllib.parse.urljoin(self.page.url, a["href"])
            return
        if tag in ("button", "select", "textarea") and not self.hidden(a):
            self.control(tag, a)
        if tag in SKIP or (tag not in VOID and self.hidden(a)):
            if tag not in VOID:
                self.skip_tag, self.skip_depth, self.skip_words = tag, 1, []
            return
        if tag in BLOCKS or tag in ("td", "th"):
            container = None
            if tag in CONTAINERS:
                self.cid += 1
                container = self.cid
            if tag in BLOCKS or container is not None:
                self.stack.append((tag, container))
        if tag in HEADINGS:
            self.block(HEADINGS[tag])
        elif tag in ("ul", "ol", "menu"):
            self.block()
            self.lists.append([tag == "ol", 0])
            self.indent += 1
        elif tag == "li":
            self.block("li")
            if self.lists:
                self.lists[-1][1] += 1
                ordered, n = self.lists[-1]
                self.add_text(f"{n}. " if ordered else "• ")
            else:
                self.add_text("• ")
        elif tag == "blockquote":
            self.block("quote")
            self.indent += 1
        elif tag == "pre":
            self.block("pre")
            self.pre += 1
        elif tag == "dd":
            self.block()
            self.indent += 1
        elif tag == "tr":
            self.block()
            self.cells = 0
        elif tag in ("td", "th"):
            if self.cells and self.runs and "".join(r[0] for r in self.runs).strip():
                self.add_text("   ")
            self.cells += 1
            if tag == "th":
                self.bold += 1
        elif tag in BLOCKS:
            self.block("small" if tag in ("figcaption", "caption") else None)
        if tag == "a":
            href = self.absolute(a.get("href"))
            if href:
                self.page.links.append(href)
                self.link = len(self.page.links) - 1
        elif tag in ("b", "strong", "dt", "summary", "legend"):
            self.bold += 1
        elif tag == "br":
            if self.runs:
                self.add_text("\n")
        elif tag == "hr":
            self.block()
            self.page.blocks.append({"kind": "rule", "in": self.containers()})
        elif tag == "img":
            self.image(a)
        elif tag == "form":
            self.block()
            self.page.forms.append({"action": self.absolute(a.get("action")) or self.page.url,
                                    "method": (a.get("method") or "get").lower(), "fields": []})
            self.form = len(self.page.forms) - 1
        elif tag == "input":
            self.input(a)

    def handle_endtag(self, tag):
        if tag == "title" and self.in_title:
            self.in_title = False
            return
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth <= 0:
                    self.skipped(tag)
            return
        if tag == "a":
            self.link = None
        elif tag in ("b", "strong", "dt", "summary", "legend", "th"):
            self.bold = max(0, self.bold - 1)
        if tag in HEADINGS or tag in ("li", "dt", "figcaption", "caption", "summary", "legend"):
            self.block()
        elif tag in ("ul", "ol", "menu"):
            self.block()
            if self.lists:
                self.lists.pop()
            self.indent = max(0, self.indent - 1)
        elif tag == "blockquote":
            self.block()
            self.indent = max(0, self.indent - 1)
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.block()
        elif tag == "dd":
            self.block()
            self.indent = max(0, self.indent - 1)
        elif tag == "form":
            self.block()
            self.form = None
        elif tag in BLOCKS:
            self.block()
        if tag in BLOCKS or tag in ("td", "th"):
            for k in range(len(self.stack) - 1, -1, -1):   # (the element closing, and any left open inside it)
                if self.stack[k][0] == tag:
                    del self.stack[k:]
                    break

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
            return
        if self.skip_tag:
            if self.skip_tag in ("button", "select"):
                self.skip_words.append(data)
                if self.choice is not None and self.choice[2] and self.choice[3] is None:
                    self.choice[3] = data.strip()
            return
        self.add_text(data)

    # -- forms: their boxes, buttons and choices --------------------------------------------------------------------
    def control(self, tag, a):
        """A <button> (a form's: its words its label, when it closes), a <select> (its choice sent with its form) or
        a <textarea> (a box to type in)."""
        if self.form is None:
            return
        if tag == "button" and (a.get("type") or "submit").lower() == "submit":
            self.flush()
            self.page.blocks.append({"kind": "button", "form": self.form, "label": "", "name": a.get("name"),
                                     "value": a.get("value", ""), "in": self.containers()})
        elif tag == "select" and a.get("name"):
            self.choice = [a["name"], None, False, None]
        elif tag == "textarea":
            self.field(a.get("name"), a.get("placeholder") or a.get("aria-label") or "Type here", "")

    def skipped(self, tag):
        """The end of something not shown: a button's words become its label; a select's choice goes with its form."""
        words = SPACES.sub(" ", "".join(self.skip_words)).strip()
        self.skip_tag, self.skip_depth, self.skip_words = None, 0, []
        if tag == "button" and self.page.blocks and self.page.blocks[-1]["kind"] == "button" \
                and not self.page.blocks[-1]["label"]:
            b = self.page.blocks[-1]
            b["label"] = words[:60] or b["value"] or "Go"
        elif tag == "select" and self.choice is not None:
            name, value, by_words, text = self.choice
            self.choice = None
            if self.form is not None and value is not None:
                self.page.forms[self.form]["fields"].append((name, text or "" if by_words else value))

    def image(self, a):
        src = a.get("src") or ""
        lazy = a.get("data-src") or a.get("data-lazy-src") or a.get("data-original")
        if lazy or src.startswith("data:") or not src:
            src = lazy or (a.get("srcset") or a.get("data-srcset") or "").split(",")[0].strip().split(" ")[0]
        url = self.absolute(src)
        alt = SPACES.sub(" ", a.get("alt") or "").strip()

        def size(v):
            try:
                return int(float(re.sub(r"px$", "", (v or "").strip())))
            except ValueError:
                return 0
        w, h = size(a.get("width")), size(a.get("height"))
        if url is None or (w and w < 8) or (h and h < 8) or url.lower().split("?")[0].endswith(".svg") \
                or len(self.page.images) >= PICTURES_MOST:
            if alt and len(alt) < 80 and self.link is not None:
                self.add_text(alt)                     # (a link that's a picture: its words, at least)
            return
        self.flush()
        self.page.images.append({"src": url, "alt": alt, "w": w, "h": h})
        self.page.blocks.append({"kind": "image", "img": len(self.page.images) - 1, "link": self.link,
                                 "in": self.containers()})

    def input(self, a):
        kind = (a.get("type") or "text").lower()
        name = a.get("name")
        if self.form is None or self.hidden(a) and kind != "hidden":
            return
        fields = self.page.forms[self.form]["fields"]
        if kind == "hidden":
            if name:
                fields.append((name, a.get("value", "")))
        elif kind in ("checkbox", "radio"):
            if name and "checked" in a:
                fields.append((name, a.get("value", "on")))
        elif kind in ("submit", "image"):
            self.flush()
            label = a.get("value") or a.get("alt") or "Go"
            self.page.blocks.append({"kind": "button", "form": self.form, "label": label, "name": name,
                                     "value": a.get("value", ""), "in": self.containers()})
        elif kind in TEXT_TYPES:
            label = a.get("placeholder") or a.get("aria-label") or a.get("title") or ""
            self.field(name, label, a.get("value", ""))

    def field(self, name, label, value):
        if self.form is None or not name:
            return
        self.flush()
        self.page.blocks.append({"kind": "field", "form": self.form, "name": name, "label": label or "Type here",
                                 "value": value, "in": self.containers()})


def read_page(url, raw, kind):
    """A Page from what came: HTML read into blocks, a picture on its own, or text."""
    page = Page(url)
    ctype = (kind or "").split(";")[0].strip().lower()
    if ctype == "application/pdf" or raw[:5] == b"%PDF-":
        page.kind, page.title, page.data = "pdf", url.rsplit("/", 1)[-1] or url, raw
        return page
    if ctype.startswith("image/"):
        page.kind, page.title = "image", url.rsplit("/", 1)[-1] or url
        page.images.append({"src": url, "alt": "", "w": 0, "h": 0, "data": raw})
        page.blocks.append({"kind": "image", "img": 0, "link": None, "in": ()})
        return page
    text = page_text(raw, kind)
    if ctype == "text/plain" or (ctype and "html" not in ctype and "xml" not in ctype
                                 and not text.lstrip().startswith("<")):
        page.kind, page.title = "text", url.rsplit("/", 1)[-1] or url
        page.blocks.append({"kind": "text", "style": "pre", "runs": [(text[:200000], None, False)], "indent": 0,
                            "in": ()})
        return page
    r = Reader(page)
    try:
        r.feed(text)
        r.close()
    except Exception:                                  # (a page HTML can't make sense of: what was read, kept)
        pass
    r.flush()
    page.title = SPACES.sub(" ", "".join(r.title)).strip()
    page.reader = article(page)
    return page


def article(page):
    """Reader: the blocks of the page's article (the container with the most paragraphs' words, the headings and
    pictures in it too), or None if there isn't one worth it."""
    score = {}
    for b in page.blocks:
        if b["kind"] != "text" or b["style"] not in ("p", "quote") or not b["in"]:
            continue
        words = sum(len(r[0]) for r in b["runs"] if r[1] is None)    # (words in links: menus, mostly)
        if words < 40:
            continue
        score[b["in"][-1]] = score.get(b["in"][-1], 0) + words
        if len(b["in"]) > 1:
            score[b["in"][-2]] = score.get(b["in"][-2], 0) + words / 2
    if not score:
        return None
    best = max(score, key=score.get)
    if score[best] < 500:
        return None
    blocks = [b for b in page.blocks if best in b["in"]]
    return blocks if len(blocks) < len(page.blocks) else None


def form_data(page, form, extra=()):
    """A form's fields as it sends them: its own (hidden ones, the boxes as they are), then those given."""
    f = page.forms[form]
    data = list(f["fields"])
    for b in page.blocks:
        if b["kind"] == "field" and b["form"] == form:
            data.append((b["name"], b.get("value", "")))
    names = {n for n, _ in extra}
    data = [(n, v) for n, v in data if n not in names] + list(extra)
    return data


def submit(page, form, extra=()):
    """(the address, the data to POST or None) a form goes to with its fields."""
    f = page.forms[form]
    data = form_data(page, form, extra)
    if f["method"] == "post":
        return f["action"], data
    p = urllib.parse.urlsplit(f["action"])
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(data), "")), None


class Loader:
    """A page fetched and read on a thread of its own (a slow site never holds the screen up); the newest asked for
    wins. on_done(page or None, error) when it's ready."""

    def __init__(self):
        self.on_done = lambda page, error: None
        self.n = 0
        self.busy = False

    def load(self, url, data=None, referer=None):
        self.n += 1
        self.busy = True
        threading.Thread(target=self.run, args=(self.n, url, data, referer), daemon=True).start()

    def run(self, n, url, data, referer):
        page, error = None, ""
        try:
            final, kind, raw = fetch(url, data=data, referer=referer)
            page = read_page(final, raw, kind)
        except WebError as ex:
            error = str(ex)
        except Exception as ex:                        # (never stuck on "loading")
            print(f"www: {url}: {ex!r}", flush=True)
            error = "Couldn't show that page"
        if n == self.n:
            self.busy = False
            self.on_done(page, error)


def picture(src, data=None):
    """A page's picture: a PIL image (its first frame, RGB), or None if it can't be had."""
    from PIL import Image
    try:
        if data is None:
            _, kind, data = fetch(src, most=PICTURE_MOST, accept="image/avif,image/webp,image/png,image/*;q=0.8")
        im = Image.open(io.BytesIO(data))
        im.draft("RGB", (1280, 1280))                  # (a big JPEG read smaller: much quicker on a Pi Zero)
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            return bg
        return im.convert("RGB")
    except Exception:
        return None


def clean_title(page):
    """A page's name for the top of the screen and its lists: its title, or its site's name."""
    t = html.unescape(page.title or "").strip()
    return t or host(page.url) or page.url
