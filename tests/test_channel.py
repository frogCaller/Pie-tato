"""Prompts from the Pi to Claude Code: coder_hooks.py --channel as Claude Code runs it (an MCP server on
stdin and stdout, the handshake as Claude Code 2.1 does it), against the web page and media mode, both
running. A prompt typed on the Bot at work goes out as a channel event, once, in order; one lost on the
way goes out again; a Pi that restarts; a password; nobody listening; the web page's remote can't send one;
which Claude Code sessions it takes them for (its command line), with the real claude command too."""
import json, os, queue, shutil, socket, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
H = SP + "/tchan"
shutil.rmtree(H, ignore_errors=True)
for d in ("pi/Music", "pi/Videos", "pi/Pictures", "pi/Documents", "laptop/project"):
    os.makedirs(f"{H}/{d}")
os.environ["HOME"] = H + "/pi"
socket.gethostname = lambda: "gpi"
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder now)
import webui
import pietato_all as g
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
    def show(self, img): self.last = img
    def show_part(self, img, box): self.last = img
    def close(self): pass


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


class Agent:
    """coder_hooks.py --channel, talked to the way Claude Code does."""

    def __init__(self, env=None, wrap=None):
        cmd = [sys.executable, SCRIPT, "--channel", PI]
        self.p = subprocess.Popen((wrap or []) + cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=dict(ENV, **(env or {})), cwd=LAPTOP)
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

    def events(self, secs=0.3):
        out = []
        while True:
            x = self.next(lambda x: x.get("method") == "notifications/claude/channel", secs)
            if x is None:
                return out
            out.append(x)

    def start(self):
        """The handshake, as Claude Code 2.1 does it: the newest MCP first, then the one before."""
        d = self.ask("server-discover-1", "server/discover", {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}})
        i = self.ask(0, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {"roots": {"listChanged": True}},
                                       "clientInfo": {"name": "claude-code", "version": "2.1.302"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return d, i

    def stop(self):
        try:
            self.p.stdin.close()
            self.p.wait(5)
        except Exception:
            self.p.kill()


def quiet():
    """Nobody listening any more (a request from a channel that's gone has had its wait)."""
    return until(lambda: not m.prompts.listening(), g.PROMPT_WAIT + g.PROMPT_LISTEN + 3)


def type_prompt(text, web=False):
    """A on the Bot at work, the prompt typed (on a keyboard, or the web page's remote), START."""
    m.web_guard = web
    m.press("a")
    if m.view != "keys":
        return False
    for ch in text:
        m.keyboard_key("char", ch)
    m.web_guard = web
    m.press("start")
    return True


# the queue on its own
P = g.AgentPrompts()
taken = []
P.on_taken = taken.append
n = P.put("one")
r1 = P.take(0)
r2 = P.take(0)
check(f"a prompt handed out: not again while it may be on its way ({[x['text'] for x in r1['prompts']]}, {r2['prompts']})",
      [x["text"] for x in r1["prompts"]] == ["one"] and r2["prompts"] == [] and not taken)
time.sleep(g.PROMPT_ACK + 0.1)
r3 = P.take(0, got=0, run=P.run)
check("...nobody said they got it: out again", [x["id"] for x in r3["prompts"]] == [n])
r4 = P.take(0, got=n, run="from-before")
check("...a 'got' from before the Pi restarted counts for nothing", r4["prompts"] == [] and P.queue and not taken)
r5 = P.take(0, got=n, run=P.run)
check("...got it: gone, and the Pi says so", r5["prompts"] == [] and not P.queue and [x["text"] for x in taken] == ["one"])
t0 = time.monotonic()
r6 = P.take(60)
check(f"waits for one at most PROMPT_WAIT ({time.monotonic() - t0:.1f} s), listening meanwhile and after",
      r6["prompts"] == [] and time.monotonic() - t0 < g.PROMPT_WAIT + 0.5 and P.listening())
got_later = []
th = threading.Thread(target=lambda: got_later.append(P.take(g.PROMPT_WAIT)))
th.start(); time.sleep(0.3)
P.put("two")
th.join()
check("...one typed while it waits goes at once", [x["text"] for x in got_later[0]["prompts"]] == ["two"])
P.put("three")
time.sleep(g.PROMPT_KEEP + 0.1)
old = P.expire()
check(f"nobody takes one: it comes back ({[x['text'] for x in old]})", [x["text"] for x in old] == ["two", "three"]
      and not P.queue)

# the channel, against a Pi that hands out one it already got, then restarts
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
script = [{"run": "r1", "prompts": [{"id": 1, "text": "a"}]},
          {"run": "r1", "prompts": [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}]},
          {"run": "r1", "prompts": [{"id": "3", "text": "bad id"}, {"id": 3, "text": ""}, {"id": True, "text": "x"}]},
          {"run": "r2", "prompts": [{"id": 1, "text": "c"}]}]
asked = []


class FakePi(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        asked.append(self.path)
        k = len(asked) - 1
        body = dict(script[k], ok=True) if k < len(script) else None
        if body is None:
            time.sleep(1)
            body = {"ok": True, "run": "r2", "prompts": []}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


fake = ThreadingHTTPServer(("127.0.0.1", 0), FakePi)
threading.Thread(target=fake.serve_forever, daemon=True).start()
real_pi, PI = PI, f"127.0.0.1:{fake.server_address[1]}"
a = Agent({"PITATO_PROMPTS": "1"})
a.start()
ev = a.events(2.0)
a.stop()
PI = real_pi
check(f"against a Pi that hands one out twice: each once {[e['params']['content'] for e in ev]}",
      [e["params"]["content"] for e in ev] == ["a", "b", "c"])
gots = [(q.split("got=")[1].split("&")[0], q.split("run=")[1].split("&")[0]) for q in asked[:5]]
check(f"...each request says the last it got, and from which run {gots}",
      gots == [("0", ""), ("1", "r1"), ("2", "r1"), ("3", "r1"), ("1", "r2")])

# the Bot at work
m.set_setting("bot_mode", "work")
m.view = "home"
m.home_sel = [a for a, _ in m.home_apps()].index("Bot")
m.press("a")
check("the Bot, at work", m.on_coder_page())
hints = m.coder_hints(m.coder.snapshot(time.monotonic()))
check(f"its buttons: {hints}", [k for k, *_ in hints][:2] == ["◀▶", "A"] and hints[1][1] == "Prompt")
m.msg = None
m.press("a")
check(f"A with no agent listening: no box, it says so ({m.msg!r})", m.view == "list" and "isn't listening" in (m.msg or ""))

# Claude Code starts the channel
a = Agent({"PITATO_PROMPTS": "1"})
d, i = a.start()
check(f"the newest MCP's server/discover: not here ({d and d.get('error')})", d and d["error"]["code"] == -32601)
res = (i or {}).get("result", {})
check(f"initialize: {res.get('protocolVersion')}, a channel, its instructions",
      res.get("protocolVersion") == "2025-11-25"
      and res.get("capabilities") == {"experimental": {"claude/channel": {}, "claude/channel/permission": {}}}
      and res.get("serverInfo", {}).get("name") == "pitato" and 'source="pitato"' in res.get("instructions", ""))
p = a.ask(1, "ping")
t = a.ask(2, "tools/list")
x = a.ask(3, "something/else")
check("ping, an empty tools/list, nothing else", p and p["result"] == {} and t and t["result"] == {"tools": []}
      and x and x["error"]["code"] == -32601)
check("...and it asks the Pi for prompts", until(m.prompts.listening, 5))

# a prompt, typed on the Pi
m.msg = None
typed = type_prompt("fix the failing test")
ev = a.events(1.0)
check(f"a prompt from the Pi: a channel event at once {[e['params'] for e in ev]}", typed and len(ev) == 1
      and ev[0]["params"]["content"] == "fix the failing test" and ev[0]["params"]["meta"] == {"from": "handheld"})
check(f"...it says it got it, and the Pi says so ({m.msg!r})", until(lambda: not m.prompts.queue, 3)
      and m.msg == "Your coding agent has your prompt" and m.prompt_draft == "")
check("...and nothing more", not a.events(1.5))

# more: in order, each once, any characters at all
for text in ("make it faster — the café’s ünïcode menu 🍕", "then run the tests\nand commit"):
    m.prompts.put(text)
ev = a.events(1.0)
check(f"two at once: in order, each once {[e['params']['content'][:12] for e in ev]}",
      [e["params"]["content"] for e in ev] == ["make it faster — the café’s ünïcode menu 🍕", "then run the tests\nand commit"])
check("...and nothing more", not a.events(2.0) and until(lambda: not m.prompts.queue, 3))

# the Pi starts again: its prompts are numbered from 1 again
m.prompts = g.AgentPrompts()
m.prompts.on_taken = m.prompt_taken
m.prompts.put("after a restart")
first = a.next(lambda x: x.get("method") == "notifications/claude/channel", g.PROMPT_WAIT + 3)
check(f"the Pi started again: its prompts still go ({first and first['params']['content']})",
      first and first["params"]["content"] == "after a restart" and not a.events(1.0))

# the web page's remote can work the screen, but can't hand your agent something to do
m.msg = None
type_prompt("rm -rf everything", web=True)
check(f"typed with the web page's remote: not sent ({m.msg!r})", not m.prompts.queue and "Pi itself" in (m.msg or "")
      and not a.events(1.0) and m.prompt_draft == "rm -rf everything")
m.web_guard = False
m.press("a")
check("...it's still there to look at, on the Pi", m.view == "keys" and m.kb["text"] == "rm -rf everything")
m.press("b")
m.prompt_draft = ""

# B: what you typed is kept for next time
m.press("a")
for ch in "half a tho":
    m.keyboard_key("char", ch)
m.press("b")
m.press("a")
check("B keeps what you typed; A brings it back", m.view == "keys" and m.kb["text"] == "half a tho")
for ch in "ught":
    m.keyboard_key("char", ch)
m.press("start")
ev = a.events(1.0)
check("...and it goes", [e["params"]["content"] for e in ev] == ["half a thought"] and m.prompt_draft == "")

# Claude Code goes: the channel stops; a prompt nobody takes comes back to you
a.stop()
check("Claude Code gone (its stdin closed): the channel stops", a.p.returncode == 0)
m.prompts.put("nobody's there")
m.msg = None
time.sleep(g.PROMPT_KEEP + 0.2)
m.tick()
check(f"a prompt nobody took: yours again ({m.prompt_draft!r}, {m.msg!r})", not m.prompts.queue
      and m.prompt_draft == "nobody's there" and "didn't take" in (m.msg or ""))
quiet()
m.msg = None
m.press("a")
check("...and nobody's listening any more: A says so", m.view == "list" and "isn't listening" in (m.msg or ""))
m.prompt_draft = ""

# a password on the web page
with open(webui.STATIC + "/webui.txt", "w") as f:
    f.write("password = it's a secret\n")
time.sleep(0.3)
a = Agent({"PITATO_PROMPTS": "1"})
a.start()
time.sleep(1.5)
check(f"with a password, none given: it asks, it's told no, it says why {a.err}", not m.prompts.listening()
      and any("password" in e for e in a.err))
a.stop()
a = Agent({"PITATO_PROMPTS": "1", "PITATO_PASSWORD": "it's a secret"})
a.start()
check("...given it: it listens", until(m.prompts.listening, 5))
type_prompt("with the password")
check("...and the prompts come", [e["params"]["content"] for e in a.events(1.0)] == ["with the password"])
a.stop()
os.remove(webui.STATIC + "/webui.txt")
quiet()

# which sessions it takes them for: Claude Code started with server:pitato
WRAP = [sys.executable, "-c", "import subprocess, sys; sys.exit(subprocess.call(sys.argv[sys.argv.index('--') + 1:]))"]
a = Agent(wrap=WRAP + ["--dangerously-load-development-channels", "server:pitato", "--"])
a.start()
check("started by a Claude Code told server:pitato: it listens", until(m.prompts.listening, 5))
a.stop()
quiet()
a = Agent(wrap=WRAP + ["--some-flag", "server:other", "--"])
d, i = a.start()
time.sleep(1.5)
check("...by any other: it says hello, but never asks for prompts (they'd drop)", i and "result" in i
      and not m.prompts.listening())
a.stop()
a = Agent({"PITATO_PROMPTS": "1"}, wrap=WRAP + ["plain", "--"])
a.start()
check("...PITATO_PROMPTS=1 says so outright", until(m.prompts.listening, 5))
a.stop()
quiet()

# with the real claude command: set up, connected, and only a channel session asks
CLAUDE = shutil.which("claude")
if CLAUDE:
    r = subprocess.run([sys.executable, SCRIPT, PI], capture_output=True, text=True, env=ENV, cwd=LAPTOP, timeout=180)
    out = (r.stdout + r.stderr).strip()
    check(f"coder_hooks.py: hooks and the channel ({out.splitlines()[-2:]})", r.returncode == 0
          and "Added the Pietato channel" in out and "server:pitato" in out)
    copy = LAPTOP + "/.claude/pitato/coder_hooks.py"
    cfg = json.load(open(LAPTOP + "/claude-config/.claude.json"))
    entry = cfg.get("mcpServers", {}).get("pitato", {})
    check(f"...in Claude Code's own settings: {entry.get('command')} {entry.get('args')}",
          entry.get("args") == [copy, "--channel", f"http://{PI}"] and os.path.isfile(copy)
          and open(copy).read() == open(SCRIPT).read() and not entry.get("env"))
    r = subprocess.run([CLAUDE, "mcp", "list"], capture_output=True, text=True, env=ENV, cwd=LAPTOP, timeout=120)
    line = next((x for x in r.stdout.splitlines() if x.startswith("pitato")), "")
    check(f"claude mcp list: {line[-14:]!r}", "Connected" in line)
    time.sleep(1)
    check("...which isn't a channel session: it doesn't ask for prompts", not m.prompts.listening())
    seen = []
    watch = threading.Thread(target=lambda: seen.append(until(m.prompts.listening, 40)))
    watch.start()
    aport = free_port()       # (the Anthropic API: a stand-in, here, so it goes the same with no internet)
    api = subprocess.Popen([sys.executable, SP + "/fake_anthropic.py", str(aport), H + "/api.log"])
    api_env = dict(ENV, ANTHROPIC_BASE_URL=f"http://127.0.0.1:{aport}", DISABLE_TELEMETRY="1",
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", DISABLE_AUTOUPDATER="1")
    for k_ in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        api_env.pop(k_, None)
    r = subprocess.run([CLAUDE, "-p", "hi", "--dangerously-load-development-channels", "server:pitato"],
                       capture_output=True, text=True, env=dict(api_env, ANTHROPIC_API_KEY="sk-ant-not-a-key"),
                       cwd=LAPTOP, timeout=120)
    watch.join()
    check(f"claude --dangerously-load-development-channels server:pitato: it asks the Pi ({seen})", seen == [True])
    # interactive, as you'd start it: how far it gets with the channel. (Channels aren't switched on for this
    # machine's Claude Code, so it stops there, after the parts that are up to the channel: it said it's a
    # channel, in the protocol that can push messages, from the first-party API.)
    import pty, select
    KEY = "sk-ant-api03-" + "x" * 70 + "AbCdEfGhIjKlMnOpQrSt"
    cfgp = LAPTOP + "/claude-config/.claude.json"
    cfg = json.load(open(cfgp))
    cfg.update(hasCompletedOnboarding=True, theme="dark", customApiKeyResponses={"approved": [KEY[-20:]], "rejected": []},
               projects={LAPTOP + "/project": {"hasTrustDialogAccepted": True, "hasCompletedProjectOnboarding": True}})
    json.dump(cfg, open(cfgp, "w"))
    tty_env = dict(api_env, ANTHROPIC_API_KEY=KEY, TERM="xterm-256color")
    shutil.rmtree(LAPTOP + "/claude-config/debug", ignore_errors=True)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(LAPTOP + "/project")
        os.execve(CLAUDE, [CLAUDE, "--debug", "--dangerously-load-development-channels", "server:pitato"], tty_env)
    said = ""
    end = time.time() + 60
    while time.time() < end and "Channel notifications" not in said:
        if select.select([fd], [], [], 0.2)[0]:
            try:
                os.read(fd, 65536)
            except OSError:
                break
        try:
            said = "".join(x for x in open(LAPTOP + "/claude-config/debug/latest") if "pitato" in x and "hannel" in x)
        except OSError:
            pass
    os.kill(pid, 9)
    os.waitpid(pid, 0)
    api.kill()
    reason = said.split("Channel notifications", 1)[-1].strip()[:90]
    check(f"interactive Claude Code takes it for a channel: {reason!r}", "registered" in said
          or "skipped: channels feature is not currently available" in said)
    r = subprocess.run([sys.executable, SCRIPT, PI, "--password", "pw"], capture_output=True, text=True, env=ENV,
                       cwd=LAPTOP, timeout=180)
    entry = json.load(open(LAPTOP + "/claude-config/.claude.json")).get("mcpServers", {}).get("pitato", {})
    check(f"a password goes to it out of sight: {entry.get('env')}", entry.get("env") == {"PITATO_PASSWORD": "pw"}
          and "pw" not in entry.get("args"))
    r = subprocess.run([sys.executable, SCRIPT, "--remove"], capture_output=True, text=True, env=ENV, cwd=LAPTOP, timeout=180)
    entry = json.load(open(LAPTOP + "/claude-config/.claude.json")).get("mcpServers", {})
    check(f"--remove: {r.stdout.strip().splitlines()}", r.returncode == 0 and "pitato" not in entry
          and "Took the Pietato channel out" in r.stdout and not os.path.exists(copy))
    r = subprocess.run([sys.executable, SCRIPT, PI, "--no-prompts"], capture_output=True, text=True, env=ENV,
                       cwd=LAPTOP, timeout=180)
    entry = json.load(open(LAPTOP + "/claude-config/.claude.json")).get("mcpServers", {})
    check(f"--no-prompts: just the hooks ({r.returncode}, {(r.stdout + r.stderr).strip().splitlines()[-2:]})",
          r.returncode == 0 and "pitato" not in entry and "Pietato channel" not in r.stdout
          and "server:pitato" not in r.stdout)
else:                                              # (GitHub's machine: the rest of it is tried there all the same)
    print("(no claude command here: that part's tried where there's one)", flush=True)
r = subprocess.run([sys.executable, SCRIPT, PI], capture_output=True, text=True,
                   env=dict(ENV, PATH="/usr/bin:/bin"), cwd=LAPTOP, timeout=60)
check(f"no claude command: it says how to add it ({r.stdout.strip().splitlines()[-1][:60]!r})", r.returncode == 0
      and "claude mcp add --scope user pitato" in r.stdout)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
