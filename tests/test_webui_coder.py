"""webui.py's routes for the Bot at work (/coder, /coder/say, /coder/hook, /coder/prompts, /coder_hooks.py),
through the real control server to the Coder: what Claude Code's hooks report, the prompts typed on the Pi
going the other way, with and without a password."""
import base64, json, math, os, shutil, socket, struct, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
H = SP + "/tcw"
shutil.rmtree(H, ignore_errors=True)
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
os.environ["HOME"] = H
socket.gethostname = lambda: "gpi"
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)
sys.path.append(ROOT + "/pitato")
import flask, webui
import pietato_all as g
webui.HOME = H
webui.STATIC = H + "/gpi-media/static"
webui.KNOWS = True
os.makedirs(webui.STATIC)
g.STATE_FILE = H + "/state.json"; g.PLEX_FILE = H + "/plex.json"; g.CACHE_DIR = H + "/cache"
g.CODER_HOLD = 0.2
g.CODER_ONCE.update({"done": 0.3, "hello": 0.3, "shrug": 0.3, "wake": 0.3, "sleep": 0.3})
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def wav(secs=0.5, rate=22050):
    pcm = struct.pack(f"<{int(secs * rate)}h", *(int(9000 * math.sin(i / 7)) for i in range(int(secs * rate))))
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body)) + body


class FB:
    w, h, same = 640, 480, True
    last, frames = None, 0
    def show(self, img): self.last = img
    def close(self): pass


print("python", sys.version.split()[0], "flask", getattr(flask, "__version__", "?"))
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
co = m.coder
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
key = "testkey123"
srv = g.serve_control(m, g.Control(), port=port, key=key)
with open(H + "/control-key", "w") as f:
    f.write(key)
webui.CONTROL = ("127.0.0.1", port)
webui.CONTROL_KEY = H + "/control-key"
c = webui.app.test_client()
B = {"base_url": "http://gpi.local:5432"}


def settle():
    """Until whatever it's doing has had its moment."""
    time.sleep(max(g.CODER_HOLD, g.CODER_ONCE.get(co.anim, 0)) + 0.12)


# ---- a pose, straight
r = c.post("/coder?pose=typing", **B)
check(f"POST /coder?pose=typing: {r.status_code} {r.get_json()}", r.status_code == 200
      and r.get_json() == {"ok": True, "pose": "typing"} and co.anim == "typing")
r = c.get("/coder", **B)
check(f"GET /coder: {r.get_json()}", r.status_code == 200 and r.get_json() == {"ok": True, "pose": "typing"})
r = c.post("/coder", **B)
check(f"no pose: {r.status_code} {r.get_json()['error']!r}", r.status_code == 400 and r.get_json()["error"].startswith("pose is one of: rest, typing"))
check("a pose it doesn't have: no", c.post("/coder?pose=dance", **B).status_code == 400
      and c.post("/coder?pose=dead", **B).status_code == 400)
check("only GET and POST", c.put("/coder?pose=done", **B).status_code == 405)
settle()
for name in webui.CODER:
    r = c.post(f"/coder?pose={name}", **B)
    if r.status_code != 200 or not r.get_json().get("ok"):
        break
check("every one of its poses", r.status_code == 200 and webui.CODER == g.CODER_POSES)
check("the old robot-style routes are gone", all(c.post(p, **B).status_code in (404, 405) for p in
                                                 ("/anim?name=typing", "/play", "/health", "/auth")))
settle()

# ---- Claude Code's hooks: what each report becomes
cases = [({"hook_event_name": "SessionStart", "source": "startup"}, "hello"),
         ({"hook_event_name": "UserPromptSubmit", "prompt": "fix the tests"}, "thinking"),
         ({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "a.py"}}, "reading"),
         ({"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {}}, "typing"),
         ({"hook_event_name": "PreToolUse", "tool_name": "Grep", "tool_input": {}}, "reading"),
         ({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "pytest"}}, "typing"),
         ({"hook_event_name": "PreToolUse", "tool_name": "Task", "tool_input": {}}, "thinking"),
         ({"hook_event_name": "PreToolUse", "tool_name": "mcp__browser__click", "tool_input": {}}, "typing"),
         ({"hook_event_name": "PostToolBatch"}, "thinking"),
         ({"hook_event_name": "PermissionRequest", "tool_name": "Bash"}, "attention"),
         ({"hook_event_name": "PermissionDenied", "tool_name": "Bash"}, "shrug"),
         ({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash"}, "error"),
         ({"hook_event_name": "Notification", "notification_type": "idle_prompt", "message": "waiting"}, "attention"),
         ({"hook_event_name": "PreCompact", "trigger": "auto"}, "thinking"),
         ({"hook_event_name": "Stop"}, "done"),
         ({"hook_event_name": "StopFailure"}, "error"),
         ({"hook_event_name": "SessionStart", "source": "resume"}, "wake"),
         ({"hook_event_name": "SessionEnd", "reason": "logout"}, "sleep")]
bad = []
for event, want in cases:
    settle()
    r = c.post("/coder/hook", json=event, **B)
    if r.status_code != 204 or r.data or co.anim != want:
        bad.append((event["hook_event_name"], event.get("tool_name"), r.status_code, r.data, co.anim, want))
check(f"each report becomes its pose, answered with nothing at all {bad}", not bad)
settle()
time.sleep(0.4)
was = co.anim
for event in ({"hook_event_name": "SessionEnd", "reason": "clear"}, {"hook_event_name": "PostToolUse", "tool_name": "Edit"},
              {"hook_event_name": "SubagentStop"}, {"nothing": "here"}):
    r = c.post("/coder/hook", json=event, **B)
    if r.status_code != 204 or co.anim != was:
        bad.append(event)
check(f"reports with nothing to show change nothing ({was})", not bad)
r = c.post("/coder/hook", data=b"this isn't JSON", content_type="text/plain", **B)
check(f"not JSON: nothing, quietly ({r.status_code})", r.status_code == 204 and not r.data)
settle()
big = json.dumps({"session_id": "x", "hook_event_name": "PreToolUse", "tool_name": "Write",
                  "tool_input": {"file_path": "big.txt", "content": "y" * (3 << 20)}})
r = c.post("/coder/hook", data=big, content_type="application/json", **B)
check(f"a big file being written ({len(big) >> 20} MB): still typing", r.status_code == 204 and co.anim == "typing")
r = c.post("/coder/hook", data=b"x" * (40 << 20), content_type="application/json", **B)
check(f"something far too big: nothing, quietly ({r.status_code})", r.status_code == 204)

# ---- clips
settle()
t0 = time.time()
r = c.post("/coder/say", data=wav(0.5), content_type="audio/wav", **B)
check(f"POST /coder/say: {r.status_code} {r.get_json()}, answered once said ({time.time() - t0:.2f} s)",
      r.status_code == 200 and r.get_json() == {"ok": True, "ms": 500} and time.time() - t0 > 0.45)
r = c.post("/coder/say?pose=thinking", data=wav(0.2), content_type="audio/wav", **B)
check(f"...thinking: {r.get_json()}", r.status_code == 200 and r.get_json()["ok"])
r = c.post("/coder/say?pose=done", data=wav(0.2), content_type="audio/wav", **B)
check(f"...in a pose with a sound of its own: {r.get_json()}", r.status_code == 400)
r = c.post("/coder/say", data=b"just some bytes", content_type="audio/wav", **B)
check(f"...not a WAV: {r.status_code} {r.get_json()}", r.status_code == 415 and r.get_json() == {"ok": False, "error": "not a WAV file"})
r = c.post("/coder/say", data=b"\0" * (webui.CLIP_MAX + 1), content_type="audio/wav", **B)
check(f"...too big: {r.status_code}", r.status_code == 413)

# ---- prompts typed on the Pi, for your agent
g.PROMPT_WAIT = 1.0
r = c.post("/coder/prompts?wait=0", **B)
j = r.get_json()
check(f"POST /coder/prompts, none waiting: {r.status_code} {j}", r.status_code == 200 and j["ok"] and j["prompts"] == []
      and len(j["run"]) == 8 and m.prompts.listening())
n = m.prompts.put("fix the failing test")
t0 = time.time()
r = c.post("/coder/prompts?wait=20", **B)
j = r.get_json()
check(f"...one waiting: at once ({time.time() - t0:.2f} s) {j['prompts']}", r.status_code == 200
      and j["prompts"] == [{"id": n, "text": "fix the failing test"}] and time.time() - t0 < 0.5)
r = c.post(f"/coder/prompts?wait=0&got={n}&run={j['run']}", **B)
check("...got, from this run: gone", r.status_code == 200 and r.get_json()["prompts"] == [] and not m.prompts.queue)
t0 = time.time()
r = c.post("/coder/prompts?wait=999", **B)
check(f"...it waits at most as long as the Pi says ({time.time() - t0:.2f} s)", r.status_code == 200
      and time.time() - t0 < g.PROMPT_WAIT + 0.6)
for q in ("wait=soon", "got=first", "wait=nan", "wait=-5", "run=<script>"):
    r = c.post("/coder/prompts?" + q, **B)
    if q in ("wait=soon", "got=first"):
        if r.status_code != 400:
            check(f"...{q}: {r.status_code}", False)
    elif r.status_code != 200:
        check(f"...{q}: {r.status_code}", False)
check("...words that aren't numbers: no; odd numbers: made sense of", True)
check("...only POST", c.get("/coder/prompts", **B).status_code == 405)

# ---- the script that sets up the hooks
r = c.get("/coder_hooks.py", **B)
check(f"the hooks' script is handed out: {r.status_code} {len(r.data)} bytes",
      r.status_code == 200 and r.data == open(ROOT + "/pitato/coder_hooks.py", "rb").read())

# the way setup.sh installs the page (a copy, elsewhere): the script is copied next to it too
import subprocess, importlib.util
setup = open(ROOT + "/setup.sh").read()
step = setup[setup.index('step "Installing the web page'):setup.index("cat > /etc/systemd/system/pitato-web.service")]
T = H + "/installed"
subprocess.run(["bash", "-c", "set -e\nHERE=" + ROOT + "\n" + step.replace("/usr/local/share/pitato", T)
                .replace('step "', 'echo "')], check=True, capture_output=True)
spec = importlib.util.spec_from_file_location("webui_installed", T + "/webui.py")
w2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w2)
w2.HOME, w2.STATIC, w2.KNOWS = webui.HOME, webui.STATIC, True
c2 = w2.app.test_client()
r = c2.get("/coder_hooks.py", **B)
check(f"installed as setup.sh does: the script is handed out ({r.status_code})", r.status_code == 200
      and r.data == open(ROOT + "/pitato/coder_hooks.py", "rb").read() and c2.get("/", **B).status_code == 200)
os.remove(T + "/coder_hooks.py")
r = c2.get("/coder_hooks.py", **B)
check(f"...and without it, a word on what to do ({r.status_code})", r.status_code == 404 and b"setup.sh" in r.data)

# ---- who may
check("not from another site", c.post("/coder?pose=done", headers={"Sec-Fetch-Site": "cross-site"}, **B).status_code == 403
      and c.post("/coder/hook", json={"hook_event_name": "Stop"}, headers={"Sec-Fetch-Site": "cross-site"}, **B).status_code == 403)
check("by another name: no", c.post("/coder?pose=done", base_url="http://evil.example").status_code == 403)
check("by its address: yes", c.get("/coder", base_url="http://192.168.1.23:5432").status_code == 200)

with open(webui.STATIC + "/webui.txt", "w") as f:
    f.write("password = s3cret pw\n")
settle()
r = c.post("/coder?pose=reading", **B)
check(f"with a password, none given: {r.status_code} {r.get_json()}", r.status_code == 401
      and r.get_json() == {"ok": False, "error": "The web page's password is needed"})
check("...a wrong one", c.post("/coder?pose=reading", headers={"Authorization": "Bearer nope"}, **B).status_code == 401)
r = c.post("/coder?pose=reading", headers={"Authorization": "Bearer s3cret pw"}, **B)
check(f"...the right one as a token: {r.get_json()}", r.status_code == 200)
basic = "Basic " + base64.b64encode(b"x:s3cret pw").decode()
check("...or the way the page asks for it", c.get("/coder", headers={"Authorization": basic}, **B).status_code == 200)
check("hooks need it too", c.post("/coder/hook", json={"hook_event_name": "Stop"}, **B).status_code == 401
      and c.post("/coder/hook", json={"hook_event_name": "Stop"}, headers={"Authorization": "Bearer s3cret pw"}, **B).status_code == 204)
check("clips too", c.post("/coder/say", data=wav(0.1), **B).status_code == 401)
check("prompts too", c.post("/coder/prompts?wait=0", **B).status_code == 401
      and c.post("/coder/prompts?wait=0", headers={"Authorization": "Bearer s3cret pw"}, **B).status_code == 200)
check("the script doesn't (nothing private in it)", c.get("/coder_hooks.py", **B).status_code == 200)
r = c.get("/api/info", headers={"Authorization": "Bearer s3cret pw"}, **B)
check(f"the token opens the Coder's door only, not the page: {r.status_code}", r.status_code == 401
      and r.headers.get("WWW-Authenticate", "").startswith("Basic"))
check("the page itself asks as before", c.get("/", **B).status_code == 401 and c.get("/", headers={"Authorization": basic}, **B).status_code == 200)
os.remove(webui.STATIC + "/webui.txt")

# ---- media mode not running
webui.CONTROL = ("127.0.0.1", 1)
r = c.post("/coder?pose=done", **B)
check(f"Pietato not answering: {r.status_code} {r.get_json()}", r.status_code == 503
      and r.get_json() == {"ok": False, "error": "Pietato isn't answering"})
check("...a hook says so with no words", (lambda r: r.status_code == 503 and not r.data)(
      c.post("/coder/hook", json={"hook_event_name": "Stop"}, **B)))
check("...and so does a clip", c.post("/coder/say", data=wav(0.1), **B).status_code == 503)
check("...and a request for prompts", c.post("/coder/prompts?wait=0", **B).status_code == 503)
srv.shutdown()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
