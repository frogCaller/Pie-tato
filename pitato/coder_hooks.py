#!/usr/bin/env python3
"""
coder_hooks.py - shows what Claude Code is doing on Pie-tato's Bot, at work, and hands Claude Code
the prompts you type there.

Run it on the computer Claude Code runs on, with your Pi's name or address:
    python3 coder_hooks.py gpi.local
It adds hooks to Claude Code's settings (~/.claude/settings.json, for all your projects) that tell
the Pi what Claude Code is doing. They run in the background, so they never hold Claude Code up,
and do nothing when the Pi is off.

It also adds a copy of itself to Claude Code as a channel called pitato, which hands Claude Code
the prompts you type on the Pi (A on the Bot at work). Claude Code takes them when you start it with
    claude --dangerously-load-development-channels server:pitato
Channels are a research preview: Claude Code asks you to confirm each time, and it needs to be
signed in to a Claude account (or use an Anthropic API key).

    --password PW   your Pi's web page password, if it has one (it's kept in the hooks)
    --here          just this project: .claude/settings.json in this folder
    --no-prompts    just the hooks, no channel
    --remove        take the hooks and the channel out again

Run it again to change the address. Your other settings and hooks stay as they are.
The Pi hands this script out too:  curl -O http://<your Pi's name>.local:5432/coder_hooks.py
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PORT = 5432                            # the Pi's web page
MARK = "/coder/hook"                   # how these hooks are told apart from yours
EVENTS = {                             # what Claude Code tells the Pi about (and which ones, for some)
    "SessionStart": None, "UserPromptSubmit": None, "PreToolUse": None, "PostToolBatch": None,
    "PermissionRequest": None, "PermissionDenied": None, "PostToolUseFailure": None,
    "Notification": "permission_prompt|idle_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input",
    "PreCompact": None, "Stop": None, "StopFailure": None,
    "SessionEnd": "logout|prompt_input_exit|other",
}
CHANNEL = "pitato"                     # the channel's name in Claude Code
OLD_CHANNELS = ("gpi-media",)          # ...and what it was called before (taken out when this one goes in)
START = f"claude --dangerously-load-development-channels server:{CHANNEL}"
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")   # the MCP versions the channel speaks
WAIT = 20                              # seconds each request for prompts waits on the Pi for one
INSTRUCTIONS = (
    f'Messages in <channel source="{CHANNEL}"> are prompts the user typed on their Pie-tato handheld '
    "(a Raspberry Pi with a small screen and game buttons). Act on each one as if they had typed it here. "
    "The handheld shows that you're working and when you're done, but not what you say, so answer here as usual.")
EMPTY = {"tools/list": "tools", "prompts/list": "prompts", "resources/list": "resources",
         "resources/templates/list": "resourceTemplates"}
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # (the Pi is on your network)


def base_url(where):
    """gpi.local -> http://gpi.local:5432"""
    where = where.strip().rstrip("/")
    if "://" not in where:
        where = "http://" + where
    scheme, rest = where.split("://", 1)
    host = rest.split("/", 1)[0]
    if ":" not in host.rsplit("]", 1)[-1]:          # (no port given; an IPv6 address is in brackets)
        host += f":{PORT}"
    return f"{scheme}://{host}"


def hook_command(url, password=""):
    """What each hook runs: Claude Code's report, sent to the Pi. Never fails (it doesn't matter if
    the Pi is off), and prints nothing (Claude Code would read it)."""
    args = ["curl", "-s", "-m", "3", "-o", "/dev/null", "-H", "Content-Type: application/json"]
    if password:
        args += ["-H", "Authorization: Bearer " + password]
    args += ["--data-binary", "@-", url + MARK]
    return " ".join(shlex.quote(a) for a in args) + " || true"


def say_hello(url, password=""):
    """The bot waves from the Pi's screen: (True, "") or (False, why not)."""
    req = urllib.request.Request(url + "/coder?pose=hello", data=b"", method="POST")
    if password:
        req.add_header("Authorization", "Bearer " + password)
    try:
        with DIRECT.open(req, timeout=5):
            return True, ""
    except urllib.error.HTTPError as ex:
        if ex.code == 401:
            return False, "the Pi's web page has a password: run this again with --password and the password"
        return False, f"the Pi answered with an error ({ex.code}). Is Pie-tato running?"
    except (OSError, ValueError) as ex:
        return False, f"couldn't reach {url} ({getattr(ex, 'reason', ex)})"


def settings_file(here):
    return os.path.join(os.getcwd() if here else os.path.expanduser("~"), ".claude", "settings.json")


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {}
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("it isn't a JSON object")
    return data


def without_ours(hooks):
    """Claude Code's hooks, minus the ones this script added."""
    out = {}
    for event, groups in (hooks if isinstance(hooks, dict) else {}).items():
        if not isinstance(groups, list):
            out[event] = groups
            continue
        kept = []
        for g in groups:
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                inner = [h for h in g["hooks"] if not (isinstance(h, dict) and MARK in str(h.get("command", "")))]
                if not inner:
                    continue
                if len(inner) != len(g["hooks"]):
                    g = dict(g, hooks=inner)
            kept.append(g)
        if kept:
            out[event] = kept
    return out


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and not os.path.exists(path + ".before-coder"):
        with open(path, encoding="utf-8") as f, open(path + ".before-coder", "w", encoding="utf-8") as b:
            b.write(f.read())                       # (how it was, the first time)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


# ---- the channel: the prompts you type on the Pi, handed to Claude Code ----------------------------
def kept_copy(name=CHANNEL):
    """Where Claude Code runs this script from: a copy that stays put (~/.claude/pitato)."""
    return os.path.join(os.path.expanduser("~"), ".claude", name, "coder_hooks.py")


def claude_mcp(args):
    """claude mcp ...: (worked, what it said), or None when there's no claude command here."""
    claude = shutil.which("claude")
    if not claude:
        return None
    try:
        r = subprocess.run([claude, "mcp"] + args, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as ex:
        return False, str(ex)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def add_channel(url, password, here):
    """This script, added to Claude Code as the channel: (True, "") or (False, why not)."""
    copy = kept_copy()
    os.makedirs(os.path.dirname(copy), exist_ok=True)
    if os.path.abspath(__file__) != os.path.abspath(copy):
        shutil.copyfile(os.path.abspath(__file__), copy)
    scope = "local" if here else "user"
    args = ["add", "--scope", scope, CHANNEL]
    if password:
        args += ["-e", "PITATO_PASSWORD=" + password]   # (kept out of its command line)
    args += ["--", sys.executable or "python3", copy, "--channel", url]
    claude_mcp(["remove", "--scope", scope, CHANNEL])  # (the one from before, if there is one)
    remove_old(here)
    got = claude_mcp(args)
    if got is None:
        return False, "there's no claude command here. Add it yourself:\n    claude mcp " + " ".join(
            shlex.quote(a) for a in args)
    if not got[0]:
        return False, got[1] or "claude mcp add didn't work"
    return True, ""


def remove_channel(here):
    """Takes the channel out of Claude Code: True if it was there."""
    got = claude_mcp(["remove", "--scope", "local" if here else "user", CHANNEL])
    if not here:
        forget_copy(CHANNEL)
    return bool(remove_old(here) or (got and got[0]))


def remove_old(here):
    """The channel by its name from before, taken out (and its copy): True if it was there."""
    was = False
    for name in OLD_CHANNELS:
        got = claude_mcp(["remove", "--scope", "local" if here else "user", name])
        was = was or bool(got and got[0])
        if not here:
            forget_copy(name)
    return was


def forget_copy(name):
    try:
        os.remove(kept_copy(name))
        os.rmdir(os.path.dirname(kept_copy(name)))
    except OSError:
        pass


def command_lines(levels=2):
    """The command lines of the process that started this one (Claude Code) and the one before it (in
    case Claude Code started it through a shell); None when there's no telling."""
    pid = os.getppid()
    if os.name == "nt":
        script = (f"$i = {int(pid)}; for ($n = 0; $n -lt {levels} -and $i; $n++) {{ "
                  "$p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $i); if (-not $p) { break }; "
                  "[Console]::WriteLine([string]$p.CommandLine); $i = $p.ParentProcessId }")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        return [line for line in r.stdout.splitlines() if line.strip()] or None
    out = []
    for _ in range(levels):
        if pid <= 1:
            break
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
            with open(f"/proc/{pid}/stat", "rb") as f:
                parent = int(f.read().rsplit(b")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            try:                                       # (no /proc: a Mac)
                r = subprocess.run(["ps", "-ww", "-o", "ppid=", "-o", "command=", "-p", str(pid)],
                                   capture_output=True, text=True, timeout=10)
                first, _, cmd = r.stdout.strip().partition(" ")
                parent = int(first)
            except (OSError, ValueError, subprocess.SubprocessError):
                return out or None
        out.append(cmd)
        pid = parent
    return out


def wanted():
    """Whether to take the Pi's prompts: only when Claude Code was started to take them from here (its
    command line names server:pitato). Any other Claude Code session would let them drop.
    PITATO_PROMPTS=1 or 0 says so outright."""
    said = os.environ.get("PITATO_PROMPTS", "").strip()
    if said in ("0", "1"):
        return said == "1"
    lines = command_lines()
    return True if lines is None else any(f"server:{CHANNEL}" in line for line in lines)


def ask_pi(url, password, got, run):
    """The Pi's prompts for Claude Code: {"run", "prompts": [{"id", "text"}]}, at once or as soon as one
    is typed (WAIT seconds at most). got: the last one handed on (from run), so the Pi knows it's here."""
    query = urllib.parse.urlencode({"wait": WAIT, "got": got, "run": run})
    req = urllib.request.Request(f"{url}/coder/prompts?{query}", data=b"", method="POST")
    if password:
        req.add_header("Authorization", "Bearer " + password)
    with DIRECT.open(req, timeout=WAIT + 15) as r:
        data = json.loads(r.read() or b"{}")
    if not isinstance(data, dict) or not data.get("ok") or not isinstance(data.get("prompts"), list):
        raise ValueError("the Pi's answer made no sense")
    return data


def hand_on(url, password, send, ready):
    """The Pi's prompts, each handed to Claude Code as it comes."""
    ready.wait(30)                                 # (Claude Code says when it's ready for them)
    if not wanted():
        return
    run, got, pause, told = "", 0, 0.0, ""

    def say(why):
        nonlocal told
        if why != told:                            # (Claude Code keeps what's said here in its logs)
            print(f"{CHANNEL}: {why}", file=sys.stderr, flush=True)
            told = why
    say(f"listening for prompts from {url}")
    while True:
        try:
            data = ask_pi(url, password, got, run)
        except urllib.error.HTTPError as ex:
            pause = 60.0 if ex.code in (401, 404) else 10.0
            say("the Pi's web page has a password: run coder_hooks.py again with --password" if ex.code == 401
                else f"the Pi answered with an error ({ex.code}): does it have the newest Pie-tato?")
        except (OSError, ValueError) as ex:
            pause = min(30.0, pause * 2 or 2.0)
            say(f"can't reach the Pi ({getattr(ex, 'reason', ex)}): trying again")
        else:
            if pause:
                say(f"listening for prompts from {url}")
            pause = 0.0
            if data.get("run") != run:             # (the Pi has started again since)
                run, got = str(data.get("run") or ""), 0
            for p in data["prompts"]:
                pid = p.get("id") if isinstance(p, dict) else None
                if not isinstance(pid, int) or isinstance(pid, bool) or pid <= got:
                    continue
                got = pid
                text = p.get("text")
                if isinstance(text, str) and text.strip():
                    send({"jsonrpc": "2.0", "method": "notifications/claude/channel",
                          "params": {"content": text, "meta": {"from": "handheld"}}})
        if pause:
            time.sleep(pause)


def channel(url, password):
    """What Claude Code runs (claude mcp add ... --channel): an MCP server on stdin and stdout, a channel
    that hands Claude Code each prompt you type on the Pi."""
    out, lock, ready = sys.stdout.buffer, threading.Lock(), threading.Event()

    def send(msg):
        data = json.dumps(msg, ensure_ascii=False).encode("utf-8") + b"\n"
        with lock:
            out.write(data)
            out.flush()
    threading.Thread(target=hand_on, args=(url, password, send, ready), daemon=True).start()
    for line in sys.stdin.buffer:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict) or not isinstance(msg.get("method"), str):
            continue                               # (an answer to something it never asked)
        method = msg["method"]
        if "id" not in msg:                        # a notification
            if method == "notifications/initialized":
                ready.set()
            continue
        if method == "initialize":
            params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
            asked = params.get("protocolVersion")
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[1],
                "capabilities": {"experimental": {"claude/channel": {}}},
                "serverInfo": {"name": CHANNEL, "version": "1.0"},
                "instructions": INSTRUCTIONS}})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
        elif method in EMPTY:                      # (it has none: asked anyway, it says so)
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {EMPTY[method]: []}})
        else:                                      # (the newest MCP's server/discover too: it speaks the one before)
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"no {method} here"}})


def main():
    ap = argparse.ArgumentParser(description="Shows what Claude Code is doing on Pie-tato's Bot, at work, "
                                             "and hands Claude Code the prompts you type there.")
    ap.add_argument("pi", nargs="?", help="your Pi's name or address, like gpi.local or 192.168.1.23")
    ap.add_argument("--password", default="", help="your Pi's web page password, if it has one")
    ap.add_argument("--here", action="store_true", help="just this project (.claude/settings.json here)")
    ap.add_argument("--no-prompts", action="store_true", help="just the hooks, no channel")
    ap.add_argument("--remove", action="store_true", help="take the hooks and the channel out again")
    ap.add_argument("--channel", action="store_true", help=argparse.SUPPRESS)    # (what Claude Code runs)
    a = ap.parse_args()
    if not a.remove and not a.pi:
        ap.error("which Pi? Give its name or address, like gpi.local")
    if a.channel:
        return channel(base_url(a.pi), a.password or os.environ.get("PITATO_PASSWORD", ""))
    path = settings_file(a.here)
    try:
        settings = load(path)
    except (OSError, ValueError) as ex:
        sys.exit(f"Couldn't read {path} ({ex}). Fix it, then run this again.")
    hooks = without_ours(settings.get("hooks"))
    if a.remove:
        if hooks:
            settings["hooks"] = hooks
        else:
            settings.pop("hooks", None)
        save(path, settings)
        print(f"Took Pie-tato's hooks out of {path}.")
        if remove_channel(a.here):
            print("Took the Pie-tato channel out of Claude Code.")
        return
    url = base_url(a.pi)
    ok, why = say_hello(url, a.password)
    if not ok and "password" in why:
        sys.exit(f"Nothing changed: {why}.")
    cmd = hook_command(url, a.password)
    for event, which in EVENTS.items():
        group = {"hooks": [{"type": "command", "command": cmd, "async": True}]}
        hooks.setdefault(event, []).append(dict({"matcher": which}, **group) if which else group)
    settings["hooks"] = hooks
    save(path, settings)
    print(f"Added Pie-tato's hooks to {path}" + (" (with your password in them)." if a.password else "."))
    print("Your Pi's bot waved hello: it's listening." if ok else
          f"Couldn't say hello just now: {why}. The hooks will work once it can be reached.")
    if os.name == "nt":
        print("On Windows, Claude Code runs these hooks with Git Bash, which comes with Git for Windows.")
    if a.no_prompts:
        remove_channel(a.here)
        return
    added, why = add_channel(url, a.password, a.here)
    if added:
        print(f"Added the Pie-tato channel to Claude Code. For prompts from the Pi, start Claude Code with:\n"
              f"    {START}\n(It asks you to confirm each time: channels are a research preview.)")
    else:
        print(f"Couldn't add the channel for prompts from the Pi: {why}")


if __name__ == "__main__":
    main()
