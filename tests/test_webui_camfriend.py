"""webui.py's routes for cameras and the friend, on the Pi's Python and Flask (3.11, 2.2.2)."""
import os, sys, socket, shutil, json
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
H = SP + "/t53"
shutil.rmtree(H, ignore_errors=True)
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
os.environ["HOME"] = H
socket.gethostname = lambda: "gpi"
sys.path.insert(0, ROOT)
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder now)
import flask, webui
webui.HOME = H
webui.STATIC = H + "/gpi-media/static"
os.makedirs(webui.STATIC)
ok_all = []
def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)
asked = []
def fake_ask(method, path, body=None, timeout=10):
    asked.append((method, path, body, timeout))
    if path.startswith("/camframe"):
        return 200, b"\xff\xd8jpeg\xff\xd9", "image/jpeg"
    return 200, json.dumps({"ok": True}).encode(), "application/json"
webui.ask_pi = fake_ask
print("python", sys.version.split()[0], "flask", getattr(flask, "__version__", "?"))
c = webui.app.test_client()
B = {"base_url": "http://gpi.local:5432"}
P = {"X-Pitato-Page": "1"}
check("cameras: only for the page", c.get("/api/pi/cameras", **B).status_code == 403
      and c.get("/api/pi/cameras", headers=P, **B).status_code == 200)
check("friend: only for the page", c.get("/api/pi/friend", **B).status_code == 403
      and c.get("/api/pi/friend", headers=P, **B).status_code == 200)
r = c.get("/api/pi/camframe?addr=127.0.0.2:5492&t=123", **B)
check(f"a camera's picture loads as an <img> would: {r.status_code} {r.mimetype}", r.status_code == 200 and r.mimetype == "image/jpeg")
check(f"its address goes on, and it may take a while: {asked[-1][1]} {asked[-1][3]}s",
      asked[-1][1] == "/camframe?addr=127.0.0.2%3A5492" and asked[-1][3] == 40)
check("not from another site", c.get("/api/pi/camframe?addr=x", headers={"Sec-Fetch-Site": "cross-site"}, **B).status_code == 403)
check("changes: JSON only", c.post("/api/pi/camera", data="do=remove&addr=x", content_type="application/x-www-form-urlencoded", **B).status_code == 415)
r = c.post("/api/pi/camera", json={"do": "add", "addr": "192.168.1.50", "name": "Desk"}, **B)
check(f"add a camera: {asked[-1][1]} {asked[-1][2]}", r.status_code == 200 and asked[-1][1] == "/camera" and asked[-1][2]["addr"] == "192.168.1.50")
check("the friend: not from another site", c.post("/api/pi/friend", json={"do": "clear"}, headers={"Sec-Fetch-Site": "cross-site"}, **B).status_code == 403)
r = c.post("/api/pi/friend", json={"do": "say", "text": "hi"}, **B)
check("the friend: say", r.status_code == 200 and asked[-1][1] == "/friend" and asked[-1][2] == {"do": "say", "text": "hi"})
check("nothing else gets through", c.get("/api/pi/nope", headers=P, **B).status_code == 404
      and c.post("/api/pi/nope", json={}, **B).status_code == 404)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
