"""Web, in the Home tab: Pietato's own browser, against pages served here (an article with its pictures, links, a
list, a quote and a search box; a form sent by POST; a redirect; a gzip'd page; one in Latin-1; a PDF; a page that
never ends; a missing one) and two big pages made in the shape of a project's page on PyPI (how quickly they're
read and laid out). Its first
page (search, an address, bookmarks, where you've been, sites), a page laid out (its words, links, pictures, boxes and
buttons), ▲▼ link to link with the page scrolling along, ◀▶ a screenful, A on a link, a box and a button, B back
(where you were kept), START, Y (bookmarks), SELECT (Reader), a picture page, a PDF kept in Documents and opened, a
slow page given up on, a page that isn't there, the screen turned. Pictures of each."""
import gzip, io, json, os, shutil, sys, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_www"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Documents")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import www as WW
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def png(colour, size):
    b = io.BytesIO(); Image.new("RGB", size, colour).save(b, "PNG"); return b.getvalue()


def jpg(colour, size):
    b = io.BytesIO(); Image.new("RGB", size, colour).save(b, "JPEG", quality=85); return b.getvalue()


PDF = io.BytesIO(); Image.new("RGB", (200, 280), (255, 255, 255)).save(PDF, "PDF"); PDF = PDF.getvalue()
WORDS = ("The Dreamcast was Sega's last console, and its games still play well today. " * 3).strip()
ARTICLE = f"""<!doctype html><html><head><meta charset="utf-8"><title>Pietato News: The Dreamcast</title></head><body>
<nav><a href="/">Home</a> <a href="/second.html">Second page</a> <a href="/go">Elsewhere</a></nav>
<header><span class="sr-only">Skip to the story</span></header>
<article><h1>The Dreamcast, again</h1>
<p>{WORDS} <a href="/second.html">Read more on the second page</a>, then come back.</p>
<figure><img src="/pic.png" width="300" height="200" alt="A blue square"><figcaption>A blue square</figcaption></figure>
<p>{WORDS}</p><p>{WORDS}</p>
<h2>Its games</h2><ul><li>Crazy Taxi</li><li>Jet Set Radio <a href="/third.html">(more)</a></li><li>Shenmue</li></ul>
<blockquote>Sega does what Nintendon't.</blockquote>
<p>{WORDS} {WORDS}</p><p>{WORDS}</p><p>{WORDS}</p>
<p><a href="/big.jpg"><img src="/big.jpg" alt="A big red picture"></a></p>
<p>{WORDS}</p><p>The end of the story. <a href="/doc.pdf">Its PDF</a>.</p>
</article>
<form action="/search" method="get"><input type="hidden" name="from" value="article"><input name="q" placeholder="Search the news"></form>
<form action="/post" method="post"><input name="name" placeholder="Your name"><input name="town" placeholder="Your town">
<input type="submit" value="Send it"></form>
<footer><a href="/latin1.html">Latin-1</a> <a href="/gz.html">Gzip</a> <a href="/missing">Missing</a></footer>
</body></html>"""
asked = []


class Site(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, code, body, kind="text/html; charset=utf-8", extra=()):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        asked.append(("GET", self.path, self.headers.get("User-Agent", "")))
        p = urllib.parse.urlsplit(self.path)
        if p.path in ("/", "/index.html"):
            return self.send(200, ARTICLE.encode())
        if p.path == "/second.html":
            return self.send(200, b"<html><head><title>Second</title></head><body><h1>The second page</h1>"
                                  b"<p>Short and sweet. <a href='/index.html'>Back home</a></p></body></html>")
        if p.path == "/third.html":
            return self.send(200, b"<html><head><title>Third</title></head><body><p>Third page here.</p></body></html>")
        if p.path == "/go":
            return self.send(302, b"", extra=[("Location", "/third.html")])
        if p.path == "/search":
            q = urllib.parse.parse_qs(p.query)
            return self.send(200, f"<html><head><title>Results</title></head><body><h1>Found for {q.get('q', [''])[0]}"
                                  f"</h1><p>from {q.get('from', [''])[0]}</p></body></html>".encode())
        if p.path == "/pic.png":
            return self.send(200, png((40, 90, 220), (300, 200)), "image/png")
        if p.path == "/big.jpg":
            return self.send(200, jpg((220, 40, 40), (1600, 1200)), "image/jpeg")
        if p.path == "/doc.pdf":
            return self.send(200, PDF, "application/pdf")
        if p.path == "/gz.html":
            return self.send(200, gzip.compress("<html><title>Squeezed</title><p>Gzip'd words</p></html>".encode()),
                             extra=[("Content-Encoding", "gzip")])
        if p.path == "/latin1.html":
            return self.send(200, "<html><title>Café</title><p>Crème brûlée à la carte</p></html>".encode("latin-1"),
                             "text/html; charset=iso-8859-1")
        if p.path == "/slow.html":
            time.sleep(4)
            return self.send(200, b"<html><title>Slow</title><p>At last</p></html>")
        if p.path[6:] in BIG:
            return self.send(200, BIG[p.path[6:]])
        return self.send(404, b"<html><title>Not here</title><p>Nothing.</p></html>")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = urllib.parse.parse_qs(self.rfile.read(n).decode())
        asked.append(("POST", self.path, data))
        return self.send(200, f"<html><title>Sent</title><p>Thanks {data.get('name', [''])[0]} from "
                              f"{data.get('town', [''])[0]}</p></html>".encode())


def big_page(name, sections, releases, tables, rows):
    """A big page in the shape of a project's page on PyPI: its menus, a long description (headings, paragraphs
    with links and code, lists, examples), its release history, tables of its files, and the rest around them."""
    out = [f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>{name} · PyPI</title>",
           "<meta name='viewport' content='width=device-width, initial-scale=1'>",
           "".join(f"<link rel='stylesheet' href='/static/css/{i}.css'>" for i in range(4)),
           "<script>" + "window.x = 1; " * 70 + "</script></head><body>",
           "<header><nav>" + "".join(f"<a href='/menu/{i}'>Menu {i}</a>" for i in range(30)) + "</nav>",
           f"<form action='/search'><input name='q' placeholder='Search projects'><button>Search</button></form>",
           f"</header><main><h1>{name} 2.32.3</h1><p>pip install {name}</p>"]
    for k in range(sections):
        out.append(f"<h2 id='part-{k}'>Part {k} of {name}</h2>")
        for j in range(3):
            out.append(f"<p>What part {k} says, in a paragraph ({j}) long enough to wrap: with "
                       f"<a href='/docs/{k}/{j}'>a link to more</a>, <code>{name}.call_{k}({j})</code>, "
                       f"<em>a word or two</em> and <a href='/issues/{k * 3 + j}'>an issue</a> about it.</p>")
        out.append("<ul>" + "".join(f"<li>a point {i} about part {k}</li>" for i in range(4)) + "</ul>")
        if k % 5 == 0:
            out.append("<pre><code>" + "\n".join(f">>> r = {name}.get('https://example.com/{i}')" for i in range(6))
                       + "</code></pre>")
    out.append("<div class='release-history'>" + "".join(
        f"<a class='card' href='/project/{name}/{i // 10}.{i % 10}.0/'><p>{i // 10}.{i % 10}.0</p>"
        f"<p><time>Jan {i % 28 + 1}, {2012 + i // 40}</time></p></a>" for i in range(releases)) + "</div>")
    for t in range(tables):
        out.append(f"<h3>Hashes for {name}-{t}.whl</h3><table><tr><th>Algorithm</th><th>Hash digest</th><th></th></tr>"
                   + "".join(f"<tr><td>SHA{r}</td><td><code>{'%064x' % (t * 1000 + r)}</code></td>"
                             f"<td><button>Copy</button></td></tr>" for r in range(rows)) + "</table>")
    out.append("</main><footer>" + "".join(f"<a href='/help/{i}'>Help {i}</a>" for i in range(40)) + "</footer>")
    out.append("</body></html>")
    return "".join(out).encode()


BIG = {"pypi_requests.html": big_page("requests", 160, 200, 6, 3),      # (as many tags as requests' own page has,
       "pypi_pillow.html": big_page("pillow", 600, 700, 86, 12)}        #  and Pillow's: 4,000 and 20,000 or so)
srv = ThreadingHTTPServer(("127.0.0.1", 0), Site)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"
WW.SEARCH = BASE + "/search?q={q}"
shots = []


class FB:
    w, h = 640, 480

    def show(self, img):
        shots.append(img.copy())

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))
pictures = {}


def draw(name):
    m.dirty = True
    m.flush()
    pictures[name] = shots[-1]
    shots[-1].save(f"{S}/{name}.png")


def settle(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.flush()
        if cond():
            return True
        time.sleep(0.03)
    return False


def typed(text):
    check(m.view == "keys", f"...a box to type in: {m.kb['title'] if m.kb else None!r}")
    m.kb["text"] = text
    m.close_keyboard(True)


def page_words():
    m.dirty = True; m.flush()
    v = m.www
    return " ".join(t for ln in v["lines"] for _, t, *_ in ln["items"])


def loaded(title):
    return lambda: m.www is not None and m.www_wait is None and m.www_on_page() and WW.clean_title(m.www["page"]) == title


def focused():
    m.dirty = True; m.flush()                     # (as it's drawn: laid out)
    v = m.www
    if v["focus"] is None:
        return None
    t = v["targets"][v["focus"]]
    if t["kind"] == "link":
        return v["page"].links[t["ref"][1]]
    return t["kind"] + ":" + (t["b"].get("label") or "")


# ---- the Home tab: Web, after the rest (Home Assistant's settings: in Settings > Home) ------------------------------

home = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Home")
m.tab, m.view = home, "list"
m.load_tab(home)
rows = [r["title"] for r in m.tab_items()]
check(rows == ["TV Remote", "Lights", "Pi-hole", "Web"],
      f"the Home tab: Web after the TV Remote, Lights and Pi-hole ({rows})")
m.sels[home] = 3
draw("home_tab")
m.press("a")
wi = m.tab_index("www")
check(m.tab == wi and m.view == "list", f"A: Web's first page ({g.LIBRARY[m.tab]['name']})")
rows = [(r["icon"], r["title"]) for r in m.tab_items()]
check(rows[:2] == [("FIND", "Search the web"), ("GO", "Go to an address")]
      and [t for i, t in rows if i == "SITE"] == [n for n, _ in WW.SITES],
      f"...search, an address, and sites made for browsers like it ({rows})")
check(not any(t.startswith("The whole web") for _, t in rows), "...no Chromium on this computer (it isn't a Pi 4 or 5 "
      "with it)")
draw("start")

# ---- going to a page ------------------------------------------------------------------------------------------------
m.sels[wi] = 1
m.press("a")
typed(BASE.replace("http://", "") + "/index.html")
check(settle(loaded("Pietato News: The Dreamcast"), 10), f"an address typed (no http://, as a browser takes it): the page "
                                                         f"({m.www and WW.clean_title(m.www['page'])})")
check(asked and asked[-1][2].startswith("Mozilla/5.0"), f"...asked for as a browser does ({asked[-1][2][:40]!r}...)")
draw("page")
words = page_words()
check("The Dreamcast, again" in words and "Sega does what Nintendon't." in words and "Crazy Taxi" in words,
      "...its words: the heading, the paragraphs, the list, the quote")
check("Skip to the story" not in words and "Pietato News" not in words, "...not what's only for screen readers, nor its "
                                                                         "title (that's along the top)")
v = m.www
kinds = [t["kind"] for t in v["targets"]]
check(kinds.count("field") == 3 and kinds.count("button") == 1 and kinds.count("link") >= 9,
      f"...its links, three boxes to type in and a button ({len(kinds)}: {kinds.count('link')} links)")
check(settle(lambda: m.www_pics.get(BASE + "/pic.png"), 10), "...its pictures, fetched as they come near the screen")
draw("page_pic")
check(v["focus"] is None, "nothing picked at first")
m.press("down")
check(focused() == BASE + "/", f"▼: the first link (Home): {focused()}")
m.press("down"); m.press("down")
check(focused() == BASE + "/go", f"▼▼: on along the links ({focused()})")
y0 = v["y"]
for _ in range(3):
    m.press("down")
check(v["y"] > y0 or focused() == BASE + "/second.html", f"...on down the page: a link further down, or the page "
                                                           f"scrolled ({y0} -> {v['y']}, {focused()})")
seen = set()
for _ in range(60):
    m.press("down")
    seen.add(focused())
check(BASE + "/third.html" in seen and BASE + "/big.jpg" in seen and "field:Search the news" in seen,
      f"▼ all the way: every link, the picture's link and the boxes, the page scrolling along ({len(seen)} picked)")
check(v["y"] > 0 and v["y"] == max(0, v["height"] - (m.www_area()[1] - m.www_area()[0])),
      f"...at the bottom of the page ({v['y']} of {v['height']})")
draw("page_bottom")
for _ in range(80):
    m.press("up")
check(v["y"] == 0 and focused() == BASE + "/", f"▲ all the way: back to the top, the first link ({v['y']}, {focused()})")
m.press("right")
check(v["y"] > 200, f"▶: a screenful down ({v['y']})")
m.press("left")
check(v["y"] == 0 and focused() == BASE + "/", f"◀: back up, the first link picked ({v['y']}, {focused()})")
m.press("down")
m.press("a")
check(settle(loaded("Second"), 10), f"A on a link: its page ({WW.clean_title(m.www['page'])})")
check(any(a[1] == "/second.html" for a in asked), "...asked for")
m.press("down")
check(focused() == BASE + "/index.html", f"...its link picked ({focused()})")
m.press("b")
check(m.www and WW.clean_title(m.www["page"]) == "Pietato News: The Dreamcast" and focused() == BASE + "/second.html",
      f"B: back where you were, the link you'd picked still picked, not fetched again ({focused()})")
n_asked = len(asked)
m.press("b")
check(not m.www_on_page() and m.view == "list" and m.tab == wi, "B again (the first page you went to): Web's first page")
rows = [(r["icon"], r["title"]) for r in m.tab_items()]
check(rows[0] == ("PAGE", "Pietato News: The Dreamcast") and ("PAST", "Pietato News: The Dreamcast") in rows
      and ("PAST", "Second") in rows, f"...the page you were on, to go back to, and where you've been ({rows[:6]})")
draw("start_back")
m.sels[wi] = 0
m.press("a")
check(m.www_on_page() and len(asked) == n_asked, "A on it: the page again, as it was (not fetched again)")
m.press("b")
m.press("b")
check(m.tab == home and m.view == "list", f"B from Web's first page: the Home tab ({g.LIBRARY[m.tab]['name']})")
m.sels[home] = 3
m.press("a")
check(m.tab == wi and not m.www_on_page(), "...and Web again: its first page")

# ---- redirects, a box, a form sent, START -------------------------------------------------------------------------
m.sels[wi] = 0
m.press("a")
v = m.www
m.www_go(BASE + "/go")
check(settle(loaded("Third"), 10), f"a redirect followed ({WW.clean_title(m.www['page'])}, {m.www['page'].url})")
check(m.www["page"].url == BASE + "/third.html", "...the address it ended at")
m.press("b")
v = m.www
while focused() != "field:Search the news":
    m.press("down")
m.press("a")
check(m.view == "keys" and m.kb["title"] == "Search the news", f"A on a box: a box to type in, named as the page names it "
                                                               f"({m.kb and m.kb['title']!r})")
typed("sega")
check(settle(loaded("Results"), 10), "...typed in it (its form's only box): its form sent")
check("Found for sega" in page_words() and "from article" in page_words(), f"...with its hidden fields ({page_words()!r})")
m.press("b")
v = m.www
while focused() != "field:Your name":
    m.press("down")
m.press("a"); typed("Sam")
check(m.www_wait is None and WW.clean_title(m.www["page"]) == "Pietato News: The Dreamcast",
      "a box in a form of two: typed in, not sent yet")
m.press("down")
check(focused() == "field:Your town", f"...the next box ({focused()})")
m.press("a"); typed("Springfield")
m.press("down")
check(focused() == "button:Send it", f"...its button ({focused()})")
draw("form")
m.press("a")
check(settle(loaded("Sent"), 10) and asked[-1][0] == "POST" and asked[-1][2] == {"name": ["Sam"], "town": ["Springfield"]},
      f"A on the button: the form sent as it says (POST), what was typed in it ({asked[-1]})")
m.press("start")
check(m.view == "keys" and m.kb["title"] == "Search, or an address", "START on a page: a box for an address or a search")
typed("jet set radio")
check(settle(loaded("Results"), 10) and "Found for jet set radio" in page_words(), "...words: a search")

# ---- kinds of page ------------------------------------------------------------------------------------------------
m.www_go(BASE + "/gz.html")
check(settle(loaded("Squeezed"), 10) and "Gzip'd words" in page_words(), "a page sent gzip'd")
m.www_go(BASE + "/latin1.html")
check(settle(loaded("Café"), 10) and "Crème brûlée à la carte" in page_words(), "a page in Latin-1, as it says")
m.www_go(BASE + "/pic.png")
check(settle(lambda: m.www_wait is None and m.www["page"].kind == "image" and m.www_pics.get(BASE + "/pic.png"), 10),
      "a picture on its own: shown")
draw("picture_page")
toasts.clear()
m.www_go(BASE + "/missing")
check(settle(lambda: m.www_wait is None, 10) and toasts and toasts[-1] == "The site said 404 (Not Found)"
      and m.www["page"].kind == "image", f"a page that isn't there: it says so, the page before still up ({toasts[-1:]})")
m.www_go("http://127.0.0.1:1/nothing")
check(settle(lambda: m.www_wait is None, 15) and toasts[-1] == "Couldn't reach that site", f"...a site that isn't: "
                                                                                            f"{toasts[-1]!r}")
m.www_go(BASE + "/slow.html")
settle(lambda: False, 0.4)
draw("loading")
check(m.www_wait is not None, "a slow page: loading (the page before still up, and it says so)")
m.press("b")
check(m.www_wait is None, "...B: given up on")
settle(lambda: False, 4.5)
check(m.www["page"].kind == "image", "...and when it comes after all, it's not put up")
m.www_go(BASE + "/doc.pdf")
check(settle(lambda: m.view == "pdf", 15), f"a PDF: kept in Documents and opened ({m.view}, {toasts[-1:]})")
check(os.path.getsize(HOME + "/Documents/doc.pdf") == len(PDF), "...in Documents, whole")
m.press("b")

# ---- bookmarks and Reader -----------------------------------------------------------------------------------------
m.tab, m.view = wi, "list"
m.www_go(BASE + "/index.html")
settle(loaded("Pietato News: The Dreamcast"), 10)
m.press("y")
check(toasts[-1].startswith("Bookmarked"), f"Y: a bookmark ({toasts[-1]!r})")
m.press("select")
v = m.www
check(v["reader"] and "Crazy Taxi" in page_words() and "Elsewhere" not in page_words() and "Gzip" not in page_words(),
      "SELECT: Reader, just the article (not the links along its top and bottom)")
draw("reader")
m.press("select")
check(not v["reader"] and "Elsewhere" in page_words(), "...SELECT again: the whole page")
m.www_go(BASE + "/second.html")
settle(loaded("Second"), 10)
m.press("select")
check(toasts[-1].startswith("Reader: this page has no article"), f"...a page with no article: it says so ({toasts[-1]!r})")
m.press("b"); m.press("b")
while m.www_on_page():
    m.press("b")
rows = m.tab_items()
marks = [(r["icon"], r["title"]) for r in rows if r["icon"] == "MARK"]
check(marks == [("MARK", "Pietato News: The Dreamcast")], f"its first page: the bookmark ({marks})")
m.sels[wi] = next(k for k, r in enumerate(rows) if r["icon"] == "MARK")
check(("Y", "Remove") in m.list_hints(), f"...Y to remove it ({m.list_hints()})")
draw("start_marks")
m.press("y")
check(not any(r["icon"] == "MARK" for r in m.tab_items()) and toasts[-1] == "Bookmark removed", "...Y: removed")
state = json.load(open(g.STATE_FILE))
check(state["www"]["recent"][0]["title"] in ("Second", "Pietato News: The Dreamcast") and not state["www"]["marks"],
      "kept with the rest of what it keeps")
m2 = g.Media()
check([r["title"] for r in m2.www_recent()] == [r["title"] for r in m.www_recent()], "...there after a restart")

# ---- big real pages: read and laid out quickly enough, ▼ through them -----------------------------------------------
for name in ("pypi_requests.html", "pypi_pillow.html"):
    t0 = time.perf_counter()
    m.www_go(BASE + "/pypi/" + name)
    settle(lambda: m.www_wait is None and m.www_on_page(), 20)
    took = time.perf_counter() - t0
    t1 = time.perf_counter()
    draw("pypi_" + name.split("_")[1].split(".")[0])
    first = time.perf_counter() - t1
    t2 = time.perf_counter()
    for _ in range(20):
        m.press("down"); m.dirty = True; m.flush()
    each = (time.perf_counter() - t2) / 20
    v = m.www
    check(took < 8 and first < 2.0 and each < 0.2 and len(v["lines"]) > 100,
          f"{name}: fetched and read in {took:.1f} s, laid out and drawn in {first * 1000:.0f} ms, then {each * 1000:.0f} "
          f"ms a press ({len(v['lines'])} lines, {len(v['targets'])} links and boxes)")
draw("pypi_moved")

# ---- the screen turned ---------------------------------------------------------------------------------------------
m.www_go(BASE + "/index.html")
settle(loaded("Pietato News: The Dreamcast"), 10)
m.press("right")
FB.w, FB.h = 480, 640
m.dirty = True; m.flush()
v = m.www
widest = max((x + w for ln in v["lines"] for x, _, _, _, _, w in ln["items"]), default=0)
check(v["laid"][0] == 480 and widest <= 480 - 20, f"a screen on its side (480 wide): laid out again to fit ({widest:.0f})")
draw("portrait")
FB.w, FB.h = 640, 480

# ---- the pictures -----------------------------------------------------------------------------------------------------
sheet = Image.new("RGB", (2 * 650 - 10, ((len(pictures) + 1) // 2) * 490), (80, 80, 80))
for k, (name, im) in enumerate(pictures.items()):
    sheet.paste(im.resize((640, 480)) if im.size != (640, 480) else im, ((k % 2) * 650, (k // 2) * 490))
sheet.save(f"{SP}/www_sheet.png")
print("pictures:", ", ".join(pictures))
srv.shutdown()
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
os._exit(0)
