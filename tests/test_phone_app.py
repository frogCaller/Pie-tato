"""The web page as an app on a phone's home screen: its manifest (its name, opening on the whole screen, its icons) and
the icons themselves at the sizes phones ask for (a rounded one, one to the edges for the phone to cut to its own
shape, the iPhone's), all of them there before any password is asked for (they've nothing private in them), the page
saying where they are, and its top bar below a phone's clock and battery when it's opened from the home screen."""
import io, json, os, re, shutil, socket, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
from PIL import Image

S = SP + "/t_phone_app"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home"
os.makedirs(H)
os.environ["HOME"] = H
sys.path.insert(0, ROOT)
sys.path.append(ROOT + "/pitato")
import webui  # noqa: E402
webui.HOME = H
webui.STATIC = H + "/pietato/static"
os.makedirs(webui.STATIC + "/fonts")
socket.gethostname = lambda: "gpi"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


c = webui.app.test_client()
NET = {"base_url": "http://gpi.local:5432"}
r = c.get("/manifest.webmanifest", **NET)
m = json.loads(r.data) if r.status_code == 200 else {}
check(f"its manifest: Pietato, opening on the whole screen, from its first page ({r.status_code}, {r.mimetype})",
      r.status_code == 200 and r.mimetype == "application/manifest+json" and m.get("name") == "Pietato"
      and m.get("short_name") == "Pietato" and m.get("display") == "standalone" and m.get("start_url") == "/")
sizes = {(i["src"], i["sizes"], i.get("purpose", "any")) for i in m.get("icons", [])}
check(f"...its icons, one a phone may cut to its own shape ({sorted(sizes)})",
      sizes == {("/icon-192.png", "192x192", "any"), ("/icon-512.png", "512x512", "any"),
                ("/icon-maskable.png", "512x512", "maskable")})
for path, size, mode in (("/icon-192.png", 192, "RGBA"), ("/icon-512.png", 512, "RGBA"),
                         ("/icon-maskable.png", 512, "RGB"), ("/apple-touch-icon.png", 180, "RGB")):
    r = c.get(path, **NET)
    im = Image.open(io.BytesIO(r.data)) if r.status_code == 200 else None
    corner = im.getpixel((0, 0)) if im else None
    middle = im.convert("RGB").getpixel((size * 15 // 32, size * 15 // 32)) if im else None   # (in the play sign)
    check(f"{path}: {size} x {size}, {'its corners see-through' if mode == 'RGBA' else 'to its edges'}, the play sign "
          f"white in the middle ({im and im.size}, {im and im.mode}, {corner}, {middle})",
          im is not None and im.size == (size, size) and im.mode == mode
          and (corner[3] == 0 if mode == "RGBA" else corner == webui.APP_BLUE) and min(middle) > 230)
open(webui.STATIC + "/webui.txt", "w").write("password = hunter2\n")
check("with a password: its manifest and icons all the same (nothing private), the page itself not",
      c.get("/manifest.webmanifest", **NET).status_code == 200 and c.get("/icon-192.png", **NET).status_code == 200
      and c.get("/apple-touch-icon.png", **NET).status_code == 200 and c.get("/", **NET).status_code == 401)
os.remove(webui.STATIC + "/webui.txt")
page = open(ROOT + "/templates/index.html").read()
check("the page says where they are, and that it opens on the whole screen from a home screen",
      '<link rel="manifest" href="/manifest.webmanifest">' in page
      and '<link rel="apple-touch-icon" href="/apple-touch-icon.png">' in page
      and '<meta name="apple-mobile-web-app-capable" content="yes">' in page
      and '<meta name="apple-mobile-web-app-title" content="Pietato">' in page)
check("...its top bar below a phone's clock and battery there (and the rest below it)",
      re.search(r"--top: calc\(64px \+ env\(safe-area-inset-top\)\)", page) is not None
      and "padding: env(safe-area-inset-top) 28px 0" in page)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
