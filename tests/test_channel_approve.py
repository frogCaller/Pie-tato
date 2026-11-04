"""Claude Code's permission prompts, answered on the Pi: coder_hooks.py --channel as Claude Code runs it says it can
relay them, passes each one on to the Pi (POST /coder/ask, through the web page), the Bot at work shows it (what,
Claude's words, the command), A allows it and B denies it (the answer back to Claude Code once, at once), X leaves it
to the computer; the web page's remote can't answer one; a prompt answered at the computer goes when Claude Code
moves on (its hooks), but not one that's only just come; nonsense from anywhere is turned away; a Pi without it
(an older Pietato) and a session that isn't taking the Pi's prompts; a password. Pictures saved."""
import json, os, queue, shutil, socket, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
H = SP + "/tapprove"
shutil.rmtree(H, ignore_errors=True)
for d in ("pi/Music", "pi/Videos", "pi/Pictures", "pi/Documents", "laptop/project", "pics"):
    os.makedirs(f"{H}/{d}")
os.environ["HOME"] = H + "/pi"
socket.gethostname = lambda: "gpi"
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder)
import urllib.request
import webui
import pietato_all as g
import numpy as np
from werkzeug.serving import make_server
webui.HOME, webui.STATIC, webui.KNOWS = H + "/pi", H + "/pi/gpi-media/static", True
os.makedirs(webui.STATIC)
g.STATE_FILE = H + "/state.json"; g.PLEX_FILE = H + "/plex.json"; g.CACHE_DIR = H + "/cache"
g.PROMPT_ACK, g.PROMPT_KEEP, g.PROMPT_LISTEN, g.PROMPT_WAIT = 1.5, 4.0, 3.0, 2.0   # (quicker)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def until(cond, secs=5.0):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


class FB:
    w, h, same = 640, 480, True
    last, frames = None, 0

    def show(self, img):
        FB.frames += 1
        self.frames = FB.frames
        self.last = img

    def show_part(self, img, box):
        self.show(img)

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
cport, key = free_port(), "k3y"
g.serve_control(m, g.Control(), port=cport, key=key)
with open(H + "/control-key", "w") as f:
    f.write(key)
webui.CONTROL, webui.CONTROL_KEY = ("127.0.0.1", cport), H + "/control-key"
wport = free_port()
httpd = make_server("127.0.0.1", wport, webui.app, threaded=True)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
PI = f"127.0.0.1:{wport}"
SCRIPT = ROOT + "/pitato/coder_hooks.py"
LAPTOP = H + "/laptop"
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PITATO", "ANTHROPIC"))}
ENV.update(HOME=LAPTOP, CLAUDE_CONFIG_DIR=LAPTOP + "/claude-config")
VERDICT = "notifications/claude/channel/permission"


class Agent:
    """coder_hooks.py --channel, talked to the way Claude Code does."""

    def __init__(self, env=None, pi=None):
        cmd = [sys.executable, SCRIPT, "--channel", pi or PI]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=dict(ENV, **(env or {})), cwd=LAPTOP)
        self.got, self.err = queue.Queue(), []
        threading.Thread(target=self.read, daemon=True).start()
        threading.Thread(target=lambda: self.err.extend(x.decode() for x in self.p.stderr), daemon=True).start()

    def read(self):
        for line in self.p.stdout:
            self.got.put(json.loads(line))

    def send(self, msg):
        self.p.stdin.write((json.dumps(msg) + "\n").encode())
        self.p.stdin.flush()

    def ask(self, mid, method, params=None):
        self.send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        return self.next(lambda x: x.get("id") == mid)

    def next(self, want=lambda x: True, secs=5.0):
        end = time.time() + secs
        while time.time() < end:
            try:
                x = self.got.get(timeout=max(0.01, end - time.time()))
            except queue.Empty:
                break
            if want(x):
                return x
        return None

    def verdicts(self, secs=0.5, first=None):
        """What it's told back (the Pi's answers): the first within first seconds (a busy machine's slower), then
        any more until none comes for secs."""
        out = []
        wait = secs if first is None else first
        while True:
            x = self.next(lambda x: x.get("method") == VERDICT, wait)
            if x is None:
                return out
            out.append(x["params"])
            wait = secs

    def start(self):
        i = self.ask(0, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                       "clientInfo": {"name": "claude-code", "version": "2.1.302"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return i

    def request(self, rid, tool="Bash", about="Run the tests", preview='{"command": "npm test"}'):
        """Claude Code's permission prompt, as it sends it to a channel."""
        self.send({"jsonrpc": "2.0", "method": "notifications/claude/channel/permission_request",
                   "params": {"request_id": rid, "tool_name": tool, "description": about, "input_preview": preview}})

    def stop(self):
        try:
            self.p.stdin.close()
            self.p.wait(5)
        except Exception:
            self.p.kill()


def waiting(rid):
    return any(a["id"] == rid for a in m.prompts.pending())


def shot(name):
    m.dirty = True
    m.flush()
    m.fb.last.save(f"{H}/pics/{name}.png")
    return m.fb.last


def hook(event, **more):
    """One of Claude Code's hooks, as coder_hooks.py's hooks send it."""
    req = urllib.request.Request(f"http://{PI}/coder/hook", data=json.dumps(dict(hook_event_name=event, **more)).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


def post_ask(body):
    req = urllib.request.Request(f"http://{PI}/coder/ask", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as ex:
        return ex.code, json.loads(ex.read() or b"{}")


# ---- the Pi's own list of them, on its own ---------------------------------------------------------------------------
P = g.AgentPrompts()
seen = []
P.on_ask = seen.append
check("a request: new, then not again", P.ask("abcde", "Bash", "x", "y") and not P.ask("abcde", "Bash", "x", "y")
      and [a["id"] for a in seen] == ["abcde"])
r0 = P.take(0)
check(f"...no answer yet: none handed out ({r0.get('verdicts')})", r0["verdicts"] == [])
got_later = []
th = threading.Thread(target=lambda: got_later.append(P.take(g.PROMPT_WAIT)))
th.start(); time.sleep(0.3)
t0 = time.monotonic()
check("answered: allow", P.answer("abcde", "allow") and not P.pending())
th.join()
check(f"...a request waiting for prompts gets it at once ({time.monotonic() - t0:.2f} s, {got_later[0]['verdicts']})",
      got_later[0]["verdicts"] == [{"request_id": "abcde", "behavior": "allow"}] and time.monotonic() - t0 < 0.5)
t0 = time.monotonic()
r1 = P.take(1.0)
check("...and again, a while, in case it was lost (no waiting for it, though)", r1["verdicts"] == got_later[0]["verdicts"]
      and time.monotonic() - t0 > 0.9)
check("an answer to one that isn't waiting, or that isn't allow or deny: nothing", not P.answer("abcde", "deny")
      and not P.answer("zzzzz", "allow") and P.ask("fghij", "Edit", "", "") and not P.answer("fghij", "yes"))
check("...nor one already answered, asked again", not P.ask("abcde", "Bash", "x", "y"))
P.ask("kmnop", "Write", "", "")
check("a request only just come: not settled by Claude Code moving on (its hooks come late)", not P.settle()
      and len(P.pending()) == 2)
time.sleep(g.ASK_GRACE + 0.1)
check("...one from a moment ago: settled (answered at the computer)", P.settle() and not P.pending())
old_keep = g.ASK_KEEP
import pitato.coder as CODER
CODER.ASK_KEEP = 0.3
P.ask("qrstu", "Bash", "", "")
time.sleep(0.4)
check("waiting too long: gone (it's the computer's)", not P.pending())
CODER.ASK_KEEP = old_keep

# ---- the channel says it relays them -----------------------------------------------------------------------------------
m.set_setting("bot_mode", "work")
m.view = "home"
m.home_sel = [a for a, _ in m.home_apps()].index("Bot")
m.press("a")
check("the Bot, at work", m.on_coder_page())
plain = shot("work")
a = Agent({"PITATO_PROMPTS": "1"})
i = a.start()
caps = ((i or {}).get("result") or {}).get("capabilities")
check(f"initialize: a channel that relays permission prompts ({caps})",
      caps == {"experimental": {"claude/channel": {}, "claude/channel/permission": {}}})
check("...and it asks the Pi for prompts", until(m.prompts.listening, 5))

# ---- a permission prompt: shown on the Bot at work ---------------------------------------------------------------
a.request("abcde")
check("Claude Code's permission prompt: on the Pi", until(lambda: waiting("abcde"), 5))
ask = m.prompts.pending()[0]
check(f"...what, its words, the command ({ask['tool']!r}, {ask['about']!r}, {ask['preview']!r})",
      ask["tool"] == "Bash" and ask["about"] == "Run the tests" and ask["preview"] == '{"command": "npm test"}')
hints = m.coder_hints(m.coder.snapshot(time.monotonic()))
check(f"...its buttons: A Allow, B Deny, X Later ({hints})", hints == [("A", "Allow"), ("B", "Deny"), ("X", "Later")])
card = shot("asks")
diff = np.abs(np.asarray(card.convert("RGB")).astype(int) - np.asarray(plain.convert("RGB")).astype(int)).max(axis=2)
check(f"...a card over its desk ({int((diff[250:425, 30:610] > 40).sum())} pixels changed there)",
      (diff[250:425, 30:610] > 40).sum() > 4000)
check(f"...the Bot looks up ({m.coder.current()})", m.coder.current() == "attention")

# A: allowed, back to Claude Code at once, once
m.web_guard = False
m.msg = None
m.press("a")
v = a.verdicts(2.0, first=8.0)
check(f"A: allowed, to Claude Code once ({v}, {m.msg!r})", v == [{"request_id": "abcde", "behavior": "allow"}]
      and m.msg == "Allowed: Bash" and not waiting("abcde"))
check("...not again, though the Pi says it a while longer", not a.verdicts(g.PROMPT_WAIT + 1.0))
after = m.coder_hints(m.coder.snapshot(time.monotonic()))
check(f"...the card gone, its usual buttons back ({after})", [k for k, *_ in after][:2] == ["◀▶", "A"])

# B: denied
a.request("fghij", tool="Write", about="Write the new config", preview='{"file_path": "/home/me/app/config.json"}')
check("another: Write", until(lambda: waiting("fghij"), 5))
shot("asks-write")
m.press("b")
v = a.verdicts(2.0, first=8.0)
check(f"B: denied ({v}, {m.msg!r}, {m.coder.current()})", v == [{"request_id": "fghij", "behavior": "deny"}]
      and m.msg == "Denied: Write" and m.coder.current() == "shrug" and m.on_coder_page())

# the web page's remote can work the screen, but can't answer one
a.request("kmnop")
until(lambda: waiting("kmnop"), 5)
m.web_guard = True
m.msg = None
m.press("a")
check(f"A from the web page's remote: not answered ({m.msg!r})", waiting("kmnop") and "Pi itself" in (m.msg or "")
      and not a.verdicts(1.0))
m.press("b")
check("...nor B", waiting("kmnop") and not a.verdicts(0.5))
btns, _ = m.web_touch({"cmd": "tap", "x": 40 / 640, "y": (480 - 24) / 480})
check(f"...tapping its button on the web page's copy: the same ({btns})", btns == ["a"])
m.press("x")
check("...X leaves it to the computer: off the screen (still there to answer at the computer)", m.coder_ask_shown() is None
      and waiting("kmnop") and m.msg == "Left for the computer to answer")
m.web_guard = False

# answered at the computer: gone once Claude Code moves on (but not one that's only just come)
a.request("qrstu")
until(lambda: waiting("qrstu"), 5)
hook("PreToolUse", tool_name="Bash")
check("its hooks about the tool it asked for: it stays", waiting("qrstu"))
hook("PostToolBatch")
check("...Claude Code moving on, a moment after it came: it stays (its hooks come late)", waiting("qrstu"))
time.sleep(g.ASK_GRACE + 0.1)
hook("Stop")
check("...moving on later: answered at the computer, gone (the one X left too)", not m.prompts.pending()
      and m.coder_ask_shown() is None)
check(f"...and done ({m.coder.current()})", until(lambda: m.coder.current() == "done", 3))
check("...and nothing went to Claude Code", not a.verdicts(1.0))

# elsewhere in media mode: a word about it
m.go_home()
m.view = "home"
m.msg = None
a.request("vwxyz", tool="WebFetch")
until(lambda: waiting("vwxyz"), 5)
check(f"on the home screen: a word about it ({m.msg!r})", "asks to use WebFetch" in (m.msg or ""))
m.home_sel = [x for x, _ in m.home_apps()].index("Bot")
m.press("a")
m.press("a")
check("...on the Bot at work: answered", a.verdicts(2.0, first=8.0) == [{"request_id": "vwxyz", "behavior": "allow"}])

# what comes from the channel is only shown, and only so much of it
long_cmd = "echo " + "x" * 5000 + "\x1b[31m‮"
a.request("abcdf", tool="Bash\nrm", about="line one\nline two\x07", preview=long_cmd)
until(lambda: waiting("abcdf"), 5)
ask = next(x for x in m.prompts.pending() if x["id"] == "abcdf")
check(f"control characters gone, one line, cut to size ({ask['tool']!r}, {len(ask['preview'])})",
      ask["tool"] == "Bash rm" and ask["about"] == "line one line two" and len(ask["preview"]) <= g.ASK_PREVIEW_MAX
      and ask["preview"].endswith("…") and "\x1b" not in ask["preview"] and "‮" not in ask["preview"])
shot("asks-long")
m.press("b")
a.verdicts(2.0, first=8.0)
for body, why in (({"request_id": "abl12", "tool_name": "Bash"}, "a made-up id"), ({"request_id": "ABCDE"}, "capitals"),
                  ({"request_id": "abcdefg"}, "too long"), ({"request_id": "zyxwv", "tool_name": 5}, "a number for words"),
                  ({"tool_name": "Bash"}, "no id")):
    code, out = post_ask(body)
    check(f"POST /coder/ask, {why}: turned away ({code}, {out})", out.get("ok") is False and not m.prompts.pending())
req = urllib.request.Request(f"http://{PI}/coder/ask", data=b"x" * (70 << 10), method="POST",
                             headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=5)
    big = 200
except urllib.error.HTTPError as ex:
    big = ex.code
check(f"...too big: turned away ({big})", big == 413)
a.stop()

# a session that isn't taking the Pi's prompts: it doesn't pass them on either
a = Agent({"PITATO_PROMPTS": "0"})
a.start()
a.request("bcdef")
time.sleep(1.0)
check("a Claude Code session not started for the Pi's prompts: its permission prompts stay at the computer",
      not waiting("bcdef"))
a.stop()

# a password on the web page
with open(webui.STATIC + "/webui.txt", "w") as f:
    f.write("password = it's a secret\n")
time.sleep(0.3)
code, _ = post_ask({"request_id": "cdefg", "tool_name": "Bash"})
check(f"with a password: none given, turned away ({code})", code == 401 and not waiting("cdefg"))
a = Agent({"PITATO_PROMPTS": "1", "PITATO_PASSWORD": "it's a secret"})
a.start()
until(m.prompts.listening, 5)
a.request("cdefg")
check("...the channel, given it: shown", until(lambda: waiting("cdefg"), 5))
m.web_guard = False
m.press("a")
vv = a.verdicts(2.0, first=8.0)
check(f"...and answered: just that one, not the last session's answers the Pi still has ({vv})",
      vv == [{"request_id": "cdefg", "behavior": "allow"}])
a.stop()
os.remove(webui.STATIC + "/webui.txt")

# a Pi without it (an older Pietato): the channel says so once, and the prompt stays at the computer
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class OldPi(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path.startswith("/coder/ask"):
            self.send_response(404)
            self.end_headers()
            return
        time.sleep(0.5)
        data = json.dumps({"ok": True, "run": "r", "prompts": []}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


old = ThreadingHTTPServer(("127.0.0.1", 0), OldPi)
threading.Thread(target=old.serve_forever, daemon=True).start()
a = Agent({"PITATO_PROMPTS": "1"}, pi=f"127.0.0.1:{old.server_address[1]}")
a.start()
time.sleep(1.0)
a.request("defgh")
a.request("efghi")
time.sleep(1.5)
a.stop()
said = [e for e in a.err if "permission prompts" in e]
check(f"an older Pi: said once ({said})", len(said) == 1 and "newest Pietato" in said[0])
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
