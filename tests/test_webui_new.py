"""webui.py's new routes on the Pi's own Python and Flask (3.11, Flask 2.2.2): the typeface,
private files, thumbnails, and other sites turned away."""
import io, os, sys, json, shutil, socket, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
H = SP + "/t41"
shutil.rmtree(H, ignore_errors=True)
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
os.environ["HOME"] = H
socket.gethostname = lambda: "gpi"
sys.path.insert(0, ROOT)
import flask
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder now)
import webui
webui.HOME = H
webui.STATIC = ST = H + "/gpi-media/static"          # the gpi-media folder, cloned into your home folder
os.makedirs(ST + "/fonts")
open(H + "/gpi-media/setup.sh", "w").write("echo hi\n")
webui.THUMBS = H + "/.cache/gpi-media/thumbs"
webui.STATE_FILE = H + "/state.json"
from PIL import Image
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


print("python", sys.version.split()[0], "flask", flask.__version__ if hasattr(flask, "__version__") else "?")
c = webui.app.test_client()
B = {"base_url": "http://gpi.local:5432"}
r = c.get("/", **B)
check("the page", r.status_code == 200 and b"Hyperlegible" in r.data)
r = c.get("/static/fonts/next-latin.woff2", **B)
check(f"typeface: {r.status_code} {r.mimetype} {r.headers.get('Cache-Control')}",
      r.status_code == 200 and r.mimetype == "font/woff2" and "immutable" in r.headers.get("Cache-Control", "")
      and r.data[:4] == b"wOF2")
check("only its own fonts", c.get("/static/fonts/..%2Fwebui.py", **B).status_code == 404
      and c.get("/static/fonts/OFL.txt", **B).status_code == 404 and c.get("/static/fonts/x.woff2", **B).status_code == 404
      and c.get("/fonts/next-latin.woff2", **B).status_code == 404)
check("other names are turned away", c.get("/static/fonts/next-latin.woff2", base_url="http://evil.example").status_code == 403)

# the static folder holds your settings: none of it handed out as it is
for name, text in (("radio.txt", "Jazz | http://x\n"), ("webui.txt", "hosts = tv.lan\n"),
                   ("homeassistant.txt", "url = x\ntoken = secret\n"), ("plex.txt", "token = t\n")):
    open(ST + "/" + name, "w").write(text)
check("nothing in static/ as it is", all(c.get("/static/" + n, **B).status_code == 404 for n in
      ("radio.txt", "webui.txt", "homeassistant.txt", "plex.txt", "fonts/OFL.txt", "../webui.py")))
check("webui.txt is read from static/", webui.settings().get("hosts") == "tv.lan"
      and c.get("/", base_url="http://tv.lan:5432").status_code == 200)
info = c.get("/api/info", **B).json
st = next(f for f in info["folders"] if f["key"] == "settings")
check(f"Files has Settings: {st}", st == {"key": "settings", "label": "Settings", "path": "~/gpi-media/static", "files": None}
      and "radio.txt" in info["settingsFiles"] and "homeFiles" not in info)
names = [e["name"] for e in c.get("/api/list?folder=settings&path=", **B).json["entries"]]
check(f"Settings lists the files you may see: {names}", names == ["radio.txt"])
os.remove(ST + "/webui.txt")

r = c.get("/api/list?folder=settings&path=", **B)
check("a token file isn't in the list", "homeassistant.txt" not in json.dumps(r.json) and "plex.txt" not in json.dumps(r.json))
check("not downloadable", c.get("/api/file?folder=settings&path=homeassistant.txt", **B).status_code in (403, 404)
      and c.get("/api/file?folder=settings&path=plex.txt", **B).status_code in (403, 404))
check("...nor through Home", c.get("/api/file?folder=home&path=gpi-media/static/homeassistant.txt", **B).status_code in (403, 404))
check("not shown on the Pi's screen", c.post("/api/pi/show", json={"folder": "settings", "path": "homeassistant.txt"}, **B).status_code in (403, 404))
check("no thumbnail of it", c.get("/api/thumb?folder=settings&path=homeassistant.txt", **B).status_code == 404)
check("radio.txt downloads", c.get("/api/file?folder=settings&path=radio.txt", **B).data == b"Jazz | http://x\n")
check("no YouTube any more", c.get("/api/youtube/key", **B).status_code == 404
      and c.get("/api/pi/youtube?list=feed", headers={"X-Pitato-Page": "1"}, **B).status_code == 404)

# thumbnails
im = Image.new("RGB", (3000, 2000), (200, 120, 40))
im.save(H + "/Pictures/big.jpg", quality=90)
r = c.get("/api/thumb?folder=pictures&path=big.jpg", **B)
small = Image.open(io.BytesIO(r.data))
check(f"a thumbnail: {small.size} {r.headers.get('Cache-Control')}", r.status_code == 200 and max(small.size) == 240
      and "private" in r.headers.get("Cache-Control", ""))
check("cached", len(os.listdir(webui.THUMBS)) == 1)
r2 = c.get("/api/thumb?folder=pictures&path=big.jpg", **B)
check("the second time from the cache", r2.status_code == 200 and len(os.listdir(webui.THUMBS)) == 1)
check("not for other kinds", c.get("/api/thumb?folder=pictures&path=../Music", **B).status_code in (403, 404))
check("nothing outside your folders", c.get("/api/thumb?folder=pictures&path=../../../etc/passwd", **B).status_code in (403, 404))
open(H + "/Pictures/broken.png", "wb").write(b"not a picture")
check("a broken picture: 404", c.get("/api/thumb?folder=pictures&path=broken.png", **B).status_code == 404)
for k in range(5):
    open(f"{webui.THUMBS}/old{k}.jpg", "wb").write(b"x")
    os.utime(f"{webui.THUMBS}/old{k}.jpg", (1, 1 + k))
webui.prune_thumbs(keep=3)
left = sorted(os.listdir(webui.THUMBS))
check(f"the cache keeps the newest: {left}", len(left) == 3 and "old0.jpg" not in left and "old4.jpg" in left)

# other websites can't make the page do things
r = c.get("/api/pi/radio?q=jazz", **B)
check("a radio search without the page's header: refused", r.status_code == 403)
r = c.get("/api/pi/catalog", headers={"X-Pitato-Page": "1"}, **B)
check(f"with it: on to the Pi ({r.status_code})", r.status_code in (200, 503))
check("pictures load without it", c.get("/api/pi/screen", **B).status_code in (200, 503))
r = c.get("/api/list?folder=music&path=", headers={"Sec-Fetch-Site": "cross-site"}, **B)
check("a request from another site: refused", r.status_code == 403)
r = c.post("/api/pi/press", json={"button": "a"}, headers={"Sec-Fetch-Site": "cross-site"}, **B)
check("...a POST too", r.status_code == 403)
check("the page itself opens from a link on another site", c.get("/", headers={"Sec-Fetch-Site": "cross-site"}, **B).status_code == 200)
check("its own requests pass", c.get("/api/list?folder=music&path=", headers={"Sec-Fetch-Site": "same-origin"}, **B).status_code == 200)

# private files dropped on the page land 0600
up = lambda folder, path, data=b"x", mode="rename": c.put(
    f"/api/upload?folder={folder}&path={path}&exists={mode}", data=data, content_type="application/octet-stream", **B)
r = up("settings", "homeassistant.txt", b"url = x\ntoken = y\n", "replace")
check(f"a token file dropped on the page lands 0600: {oct(os.stat(ST + '/homeassistant.txt').st_mode & 0o777)}",
      r.status_code == 200 and os.stat(ST + "/homeassistant.txt").st_mode & 0o777 == 0o600)
r = up("settings", "radio.txt", b"Rock | http://y\n")
check("a settings file dropped again replaces the old one (a second one would never be read)",
      r.status_code == 200 and r.json["name"] == "radio.txt" and open(ST + "/radio.txt").read() == "Rock | http://y\n"
      and os.stat(ST + "/radio.txt").st_mode & 0o777 != 0o600 and sorted(os.listdir(ST)) ==
      ["fonts", "homeassistant.txt", "plex.txt", "radio.txt"])
r = up("settings", "Crypto.TXT", b"coins = bitcoin\n")
check("...under the name media mode looks for", r.status_code == 200 and os.path.exists(ST + "/crypto.txt"))
check("skip keeps the one there", up("settings", "radio.txt", b"z", "skip").json.get("skipped")
      and open(ST + "/radio.txt").read() == "Rock | http://y\n")
check("Settings takes only settings files", up("settings", "notes.txt").status_code == 403
      and up("settings", "sub/radio.txt").status_code == 403 and up("settings", "fonts/x.woff2").status_code == 403)
check("...and never webui.txt", up("settings", "webui.txt", b"password =\n").status_code == 403
      and not os.path.exists(ST + "/webui.txt"))
check("its typeface folder isn't listed, and stays", c.post("/api/delete", json={"folder": "settings", "path": "fonts"}, **B).status_code in (403, 404)
      and os.path.isdir(ST + "/fonts"))
check("a settings file can be deleted", c.post("/api/delete", json={"folder": "settings", "path": "crypto.txt"}, **B).status_code == 200
      and not os.path.exists(ST + "/crypto.txt"))
r = up("home", "radio.txt")
check("Home: other files as usual", r.status_code == 200 and os.path.exists(H + "/radio.txt"))

# Home leaves the gpi-media folder alone (setup.sh runs from there, as root)
r = up("home", "gpi-media/setup.sh", b"rm -rf /\n", "replace")
check(f"Home can't change gpi-media's files: {r.status_code} {r.json}", r.status_code == 403
      and open(H + "/gpi-media/setup.sh").read() == "echo hi\n")
check("...or add to them", up("home", "gpi-media/evil.py").status_code == 403 and up("home", "gpi-media/static/radio.txt").status_code == 403
      and not os.path.exists(H + "/gpi-media/evil.py"))
check("...or delete them", c.post("/api/delete", json={"folder": "home", "path": "gpi-media/setup.sh"}, **B).status_code == 403
      and os.path.exists(H + "/gpi-media/setup.sh"))
rows = {e["name"]: e for e in c.get("/api/list?folder=home&path=gpi-media", **B).json["entries"]}
check(f"...and lists them locked: {sorted(rows)}", rows["setup.sh"].get("locked") and rows["static"].get("locked"))
os.symlink(H + "/gpi-media", H + "/link")
check("...not through a link either", up("home", "link/setup.sh", b"x", "replace").status_code == 403
      and open(H + "/gpi-media/setup.sh").read() == "echo hi\n")
os.remove(H + "/link")

# the review: the password never goes missing quietly, and Settings is only the settings files
check("webui.txt can't be deleted from the page", c.post("/api/delete", json={"folder": "settings", "path": "webui.txt"}, **B).status_code in (403, 404))
check("...nor anything in static/ besides settings files", c.post("/api/delete", json={"folder": "settings", "path": "fonts/OFL.txt"}, **B).status_code == 404
      and c.get("/api/file?folder=settings&path=fonts/OFL.txt", **B).status_code == 404)
open(ST + "/webui.txt.save", "w").write("password = old\n")
open(ST + "/homeassistant.txt~", "w").write("token = old\n")
listed = json.dumps(c.get("/api/list?folder=home&path=gpi-media/static", **B).json)
check("an editor's copy of a private file is private too",
      ".save" not in listed and "txt~" not in listed
      and c.get("/api/file?folder=home&path=gpi-media/static/webui.txt.save", **B).status_code == 403
      and c.get("/api/file?folder=home&path=gpi-media/static/homeassistant.txt~", **B).status_code == 403)
check("webui.txt can't be dropped anywhere", all(up(f, n).status_code == 403 for f, n in
      (("home", "webui.txt"), ("music", "WebUI.TXT"), ("documents", "webui.txt.save"), ("settings", "webui.txt"))))
open(H + "/webui.txt", "w").write("password = fromhome\n")          # where an earlier version kept it
check("one still in your home folder counts until setup.sh moves it", c.get("/api/info", **B).status_code == 401)
os.remove(H + "/webui.txt")
check("...and without it, no password", c.get("/api/info", **B).status_code == 200)
os.mkdir(ST + "/webui.txt")
check(f"a webui.txt that can't be read: the page won't open ({c.get('/', **B).status_code})", c.get("/", **B).status_code == 503
      and c.get("/api/info", **B).status_code == 503)
os.rmdir(ST + "/webui.txt")
webui.STATIC = H + "/gone/static"
r = c.get("/", **B)
check(f"no static folder (moved, deleted): the page says so rather than opening ({r.status_code} {r.data[:60]!r})",
      r.status_code == 503 and b"setup.sh" in r.data)
webui.STATIC = ST
webui.KNOWS = False
check("a copy that doesn't know where its settings are: the page says so", c.get("/", **B).status_code == 503)
webui.KNOWS = True
os.makedirs(H + "/Documents/projects/gpi-media/static")
webui.STATIC = H + "/Documents/projects/gpi-media/static"
check("a folder with the gpi-media folder in it can't be deleted", c.post("/api/delete", json={"folder": "documents", "path": "projects"}, **B).status_code == 403
      and os.path.isdir(H + "/Documents/projects/gpi-media/static"))
check("...nor what's in it changed from Documents", up("documents", "projects/gpi-media/setup.sh").status_code == 403)
webui.STATIC = ST
check("no folder called webui.txt either (it would lock the page)", up("home", "webui.txt/x").status_code == 403
      and up("documents", "a/WebUI.txt/b.txt").status_code == 403 and not os.path.exists(H + "/webui.txt"))
os.mkdir(H + "/webui.txt")                             # made some other way: not a password, the page opens
check("a folder called webui.txt in your home folder isn't taken for one", c.get("/api/info", **B).status_code == 200)
os.rmdir(H + "/webui.txt")
open(H + "/Documents/complex.txt", "w").write("x")
names = [e["name"] for e in c.get("/api/list?folder=documents&path=", **B).json["entries"]]
check(f"complex.txt is just a file: {names}", "complex.txt" in names
      and c.get("/api/file?folder=documents&path=complex.txt", **B).status_code == 200)

# thumbnails: huge pictures keep their icon, big JPEGs shrink as they load
Image.new("RGB", (6000, 6000), (10, 20, 30)).save(H + "/Pictures/huge.png")
check("a 36-megapixel PNG: no thumbnail (the Pi's memory)", c.get("/api/thumb?folder=pictures&path=huge.png", **B).status_code == 404)
Image.new("RGB", (8000, 6000), (90, 20, 30)).save(H + "/Pictures/huge.jpg", quality=60)
r = c.get("/api/thumb?folder=pictures&path=huge.jpg", **B)
check(f"a 48-megapixel JPEG: thumbnail {Image.open(io.BytesIO(r.data)).size if r.status_code == 200 else r.status_code}", r.status_code == 200)
check("HEAD without the header: refused too", c.head("/api/pi/radio?q=jazz", **B).status_code == 403)
Image.new("RGB", (3000, 2000), (10, 90, 30)).save(H + "/Pictures/big.webp")
check("a 6-megapixel WebP: its icon (WebP needs a lot of memory)", c.get("/api/thumb?folder=pictures&path=big.webp", **B).status_code == 404)
Image.new("RGB", (1600, 1200), (10, 90, 30)).save(H + "/Pictures/small.webp")
check("a 2-megapixel WebP: a thumbnail", c.get("/api/thumb?folder=pictures&path=small.webp", **B).status_code == 200)

# ---- the bot: your newest pictures to send it, and a picture passed on as where it really is ----------------
os.makedirs(H + "/Pictures/Trips/.hidden")
for rel, age in (("Trips/old.jpg", 500), ("new.png", 10), ("Trips/.hidden/secret.jpg", 1), ("notes.txt", 1),
                 ("homeassistant.txt.jpg", 1)):
    Image.new("RGB", (40, 30), (9, 9, 9)).save(H + "/Pictures/" + rel, "PNG" if rel.endswith(".png") else "JPEG") \
        if not rel.endswith(".txt") else open(H + "/Pictures/" + rel, "w").write("x")
    os.utime(H + "/Pictures/" + rel, (time.time() - age, time.time() - age))
paths = [x["path"] for x in c.get("/api/recent?n=200", **B).json["pictures"]]
mine = [p for p in paths if p in ("new.png", "Trips/old.jpg")]
check(f"recent pictures: newest first, in folders too: {paths}", mine == ["new.png", "Trips/old.jpg"])
check("...only pictures, and no hidden or private ones", all(p.endswith((".jpg", ".png", ".webp")) and ".hidden" not in p
                                                            and "homeassistant" not in p for p in paths))
check("...as many as asked for", len(c.get("/api/recent?n=2", **B).json["pictures"]) == 2)
sent = []
real_ask = webui.ask_pi
webui.ask_pi = lambda method, path, body=None, timeout=10: (sent.append((path, body)), (200, b'{"ok": true}', "application/json"))[1]
r = c.post("/api/pi/friend", json={"do": "say", "text": "hi", "picture": {"folder": "pictures", "path": "Trips/old.jpg"}}, **B)
check(f"a picture for the bot goes to the Pi as where it is: {sent[-1][1].get('picture') if sent else None}",
      r.status_code == 200 and sent[-1][1]["picture"] == os.path.realpath(H + "/Pictures/Trips/old.jpg"))
n = len(sent)
for bad in ({"folder": "pictures", "path": "../.bashrc"}, {"folder": "pictures", "path": "notes.txt"},
            {"folder": "settings", "path": "radio.txt"}, {"folder": "pictures", "path": "homeassistant.txt.jpg"},
            "/etc/passwd", {"folder": "pictures", "path": "Trips"}):
    r = c.post("/api/pi/friend", json={"do": "say", "text": "x", "picture": bad}, **B)
    check(f"...not {bad!r}: {r.status_code}", r.status_code in (400, 403, 404))
check("...none of those reached the Pi", len(sent) == n)
r = c.get("/api/pi/friendpic?id=0123456789abcdef", **B)
check(f"its pictures: kept a day ({r.headers.get('Cache-Control')})", r.headers.get("Cache-Control") == "private, max-age=86400"
      and sent[-1][0] == "/friendpic?id=0123456789abcdef")
webui.ask_pi = real_ask
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
