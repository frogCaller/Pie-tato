"""coder_hooks.py on 'the computer Claude Code runs on': fetched from the Pi with curl, run, and its
hooks then run exactly as Claude Code runs a command hook (sh -c, the report on stdin), against the
web page and media mode, both running. Your own hooks and settings stay; a password; --here; --remove."""
import json, os, shutil, socket, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
H = SP + "/tch"
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
g.CODER_HOLD = 0.2
g.CODER_ONCE.update({"done": 0.3, "hello": 0.3, "shrug": 0.3, "wake": 0.3, "sleep": 0.3})
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


class FB:
    w, h, same = 640, 480, True
    last, frames = None, 0
    def show(self, img): self.last = img
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
co = m.coder
cport, key = free_port(), "k3y"
g.serve_control(m, g.Control(), port=cport, key=key)
with open(H + "/control-key", "w") as f:
    f.write(key)
webui.CONTROL, webui.CONTROL_KEY = ("127.0.0.1", cport), H + "/control-key"
wport = free_port()
httpd = make_server("127.0.0.1", wport, webui.app, threaded=True)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
PI = f"127.0.0.1:{wport}"
LAPTOP = H + "/laptop"
PROJ = LAPTOP + "/project"
SETTINGS = LAPTOP + "/.claude/settings.json"
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PITATO"))}
ENV.update(HOME=LAPTOP, CLAUDE_CONFIG_DIR=LAPTOP + "/claude-config")     # (its own Claude Code settings)
waves = []
real_ask = co.ask
co.ask = lambda name, agent=True: (waves.append(name), real_ask(name, agent))[1]


def run(args, cwd=LAPTOP):
    r = subprocess.run(args, capture_output=True, text=True, cwd=cwd, env=ENV, timeout=60)
    return r.returncode, (r.stdout + r.stderr).strip()


def settle():
    time.sleep(max(g.CODER_HOLD, g.CODER_ONCE.get(co.anim, 0)) + 0.12)


def hooks_of(path=SETTINGS):
    return json.load(open(path)).get("hooks", {})


def ours(path=SETTINGS):
    """(event, matcher, the hook) for each of the script's hooks."""
    out = []
    for event, groups in hooks_of(path).items():
        for grp in groups:
            for h in grp["hooks"]:
                if "/coder/hook" in h.get("command", ""):
                    out.append((event, grp.get("matcher"), h))
    return out


def fire(event, path=SETTINGS):
    """Run a hook the way Claude Code does a command hook: sh -c, its report on stdin."""
    cmd = next(h["command"] for e, _, h in ours(path) if e == event["hook_event_name"])
    t0 = time.time()
    r = subprocess.run(["sh", "-c", cmd], input=json.dumps(event), capture_output=True, text=True, env=ENV, timeout=30)
    return r.returncode, r.stdout, r.stderr, time.time() - t0


# fetched from the Pi, the way the Bot at work says
rc, out = run(["curl", "-s", "-O", f"http://{PI}/coder_hooks.py"])
SCRIPT = LAPTOP + "/coder_hooks.py"
check(f"curl -O gets the script from the Pi ({rc})", rc == 0 and open(SCRIPT, "rb").read() ==
      open(ROOT + "/pitato/coder_hooks.py", "rb").read())

# someone's own settings and hooks, already there
os.makedirs(LAPTOP + "/.claude")
mine = {"model": "opus", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}],
                                    "PostToolUse": [{"hooks": [{"type": "command", "command": "prettier --write"}]}]}}
json.dump(mine, open(SETTINGS, "w"), indent=2)
settle()
rc, out = run([sys.executable, SCRIPT, PI])
check(f"run: {out!r}", rc == 0 and "Added Pietato's hooks to" in out and "bot waved hello" in out)
check(f"...and it did wave: {waves}", waves[:1] == ["hello"])
mcp = json.load(open(LAPTOP + "/claude-config/.claude.json")).get("mcpServers", {}) if shutil.which("claude") else {}
check(f"...and the channel for prompts is in Claude Code: {mcp.get('pitato', {}).get('args')}",
      not shutil.which("claude") or mcp.get("pitato", {}).get("args", [])[-2:] == ["--channel", f"http://{PI}"])
h = hooks_of()
mine_kept = (json.load(open(SETTINGS))["model"] == "opus" and h["PostToolUse"] == mine["hooks"]["PostToolUse"]
             and h["PreToolUse"][0] == mine["hooks"]["PreToolUse"][0])
check("your own settings and hooks stay as they were", mine_kept)
found = ours()
events = sorted(e for e, _, _ in found)
check(f"its hooks: {len(found)} ({', '.join(events)})", len(found) == 12 and len(set(events)) == 12
      and all(h_["type"] == "command" and h_["async"] is True for _, _, h_ in found))
matchers = {e: mt for e, mt, _ in found if mt}
check(f"which notifications and endings: {matchers}", matchers == {
    "Notification": "permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input",
    "SessionEnd": "logout|prompt_input_exit|other"})
check("a copy of how the settings were", json.load(open(SETTINGS + ".before-coder")) == mine)

# Claude Code at work: each hook as it would run it
session = [({"hook_event_name": "SessionStart", "source": "startup", "session_id": "s1", "cwd": PROJ}, "hello"),
           ({"hook_event_name": "UserPromptSubmit", "prompt": "make the tests pass"}, "thinking"),
           ({"hook_event_name": "PreToolUse", "tool_name": "Grep", "tool_input": {"pattern": "def test_"}}, "reading"),
           ({"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "a.py", "old_string": "x", "new_string": "y"}}, "typing"),
           ({"hook_event_name": "PostToolBatch"}, "thinking"),
           ({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "pytest -q"}}, "typing"),
           ({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "error": "1 failed"}, "error"),
           ({"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": "rm -rf build"}}, "attention"),
           ({"hook_event_name": "PermissionDenied", "tool_name": "Bash"}, "shrug"),
           ({"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": "b.py", "content": "z" * 2_500_000}}, "typing"),
           ({"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": "Claude needs your permission"}, "attention"),
           ({"hook_event_name": "PreCompact", "trigger": "auto"}, "thinking"),
           ({"hook_event_name": "Stop", "stop_hook_active": False}, "done"),
           ({"hook_event_name": "StopFailure"}, "error"),
           ({"hook_event_name": "SessionEnd", "reason": "logout"}, "sleep")]
wrong, said, slow = [], [], []
for event, want in session:
    settle()
    rc, so, se, took = fire(event)
    if rc != 0 or co.anim != want:
        wrong.append((event["hook_event_name"], event.get("tool_name"), rc, co.anim, want))
    if so or se:
        said.append((event["hook_event_name"], so, se))
    slow.append(took)
check(f"a session, hook by hook, the coder acting it out {wrong}", not wrong)
check(f"...the hooks print nothing (Claude Code would read it) {said}", not said)
check(f"...quick: {max(slow):.2f} s at most", max(slow) < 2)

# the Pi off
json_bad = json.load(open(SETTINGS))
for groups in json_bad["hooks"].values():
    for grp in groups:
        for h_ in grp["hooks"]:
            h_["command"] = h_["command"].replace(PI, "127.0.0.1:9")
json.dump(json_bad, open(LAPTOP + "/off.json", "w"))
rc, so, se, took = fire({"hook_event_name": "Stop"}, LAPTOP + "/off.json")
check(f"the Pi off: nothing goes wrong, nothing said ({rc}, {took:.2f} s)", rc == 0 and not so and not se and took < 4)

# again, with another address: no doubles
rc, out = run([sys.executable, SCRIPT, "gpi.local"])
found = ours()
check(f"again, another address: {out.splitlines()[-1]!r}", rc == 0 and len(found) == 12
      and all("http://gpi.local:5432/coder/hook" in h_["command"] for _, _, h_ in found) and "Couldn't say hello" in out)
rc, out = run([sys.executable, SCRIPT, PI])
check("...and back", rc == 0 and len(ours()) == 12 and all(PI in h_["command"] for _, _, h_ in ours()))

# a password on the web page
with open(webui.STATIC + "/webui.txt", "w") as f:
    f.write("password = it's a secret\n")
time.sleep(0.3)
before = open(SETTINGS).read()
rc, out = run([sys.executable, SCRIPT, PI])
check(f"with a password, none given: {out!r}", rc != 0 and "password" in out and open(SETTINGS).read() == before)
rc, out = run([sys.executable, SCRIPT, PI, "--password", "wrong"])
check("...a wrong one: nothing changes", rc != 0 and open(SETTINGS).read() == before)
settle()
rc, out = run([sys.executable, SCRIPT, PI, "--password", "it's a secret"])
check(f"...the right one: {out.splitlines()[0]!r}", rc == 0 and "with your password in them" in out and "waved" in out)
settle()
rc, so, se, took = fire({"hook_event_name": "Stop"})
check(f"...its hooks get in with it (a quote in it and all): {co.anim}", rc == 0 and not so and co.anim == "done")
os.remove(webui.STATIC + "/webui.txt")
rc, out = run([sys.executable, SCRIPT, PI])

# just one project
rc, out = run([sys.executable, SCRIPT, PI, "--here"], cwd=PROJ)
check(f"--here: {out.splitlines()[0]!r}", rc == 0 and len(ours(PROJ + "/.claude/settings.json")) == 12)
rc, out = run([sys.executable, SCRIPT, "--remove", "--here"], cwd=PROJ)
check("--remove --here", rc == 0 and "hooks" not in json.load(open(PROJ + "/.claude/settings.json")))

# taken out again
rc, out = run([sys.executable, SCRIPT, "--remove"])
after = json.load(open(SETTINGS))
mcp = json.load(open(LAPTOP + "/claude-config/.claude.json")).get("mcpServers", {}) if shutil.which("claude") else {}
check(f"--remove: {out!r}", rc == 0 and after == mine and "pitato" not in mcp)

# a broken settings file is left alone
open(SETTINGS, "w").write('{"hooks": {,}')
rc, out = run([sys.executable, SCRIPT, PI])
check(f"a broken settings file: {out!r}", rc != 0 and "Fix it" in out and open(SETTINGS).read() == '{"hooks": {,}')
rc, out = run([sys.executable, SCRIPT])
check(f"no Pi given: {out.splitlines()[-1]!r}", rc != 0)
httpd.shutdown()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
