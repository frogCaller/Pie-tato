"""coder_hooks.py after the rename, on a computer that ran the old one (gpi-media): its hooks replaced, not doubled,
and the old channel (and its copy) taken out as the new one goes in; --remove takes both out. With the real claude
command, in a home and Claude Code config of its own."""
import json, os, shutil, subprocess, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
OLD = SP + "/gpi-media.before_rename/coder_hooks.py"
NEW = ROOT + "/pitato/coder_hooks.py"
H = SP + "/t_hooks_rename"
shutil.rmtree(H, ignore_errors=True)
LAPTOP = H + "/laptop"
os.makedirs(LAPTOP + "/claude-config")
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PITATO", "GPI_MEDIA", "ANTHROPIC"))}
ENV.update(HOME=LAPTOP, CLAUDE_CONFIG_DIR=LAPTOP + "/claude-config")
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def run(script, *args):
    r = subprocess.run([sys.executable, script, *args], capture_output=True, text=True, env=ENV, cwd=LAPTOP, timeout=300)
    return r.returncode, r.stdout + r.stderr


def servers():
    try:
        return json.load(open(LAPTOP + "/claude-config/.claude.json")).get("mcpServers", {})
    except (OSError, ValueError):
        return {}


def hooks():
    settings = LAPTOP + "/claude-config/settings.json"
    if not os.path.exists(settings):
        settings = LAPTOP + "/.claude/settings.json"
    try:
        h = json.load(open(settings)).get("hooks", {})
    except (OSError, ValueError):
        return 0
    return sum(len(g.get("hooks", [])) for groups in h.values() for g in groups)


if not shutil.which("claude"):
    print("FAIL no claude command here (Claude Code's): it's what this test is about")
    sys.exit(1)

rc, out = run(OLD, "127.0.0.1:1")
print(out.strip().splitlines()[:3])
check(rc == 0 and "gpi-media" in servers() and os.path.exists(LAPTOP + "/.claude/gpi-media/coder_hooks.py"),
      "the old one: its channel and copy in")
n_old = hooks()
check(n_old > 0, f"...and its hooks ({n_old})")

rc, out = run(NEW, "127.0.0.1:1")
print(out.strip().splitlines()[:4])
s = servers()
check(rc == 0 and "pitato" in s and "gpi-media" not in s, f"the new one: its channel in, the old one out ({sorted(s)})")
check(os.path.exists(LAPTOP + "/.claude/pitato/coder_hooks.py") and not os.path.exists(LAPTOP + "/.claude/gpi-media"),
      "...its copy kept, the old copy gone")
check(hooks() == n_old, f"...the hooks replaced, not doubled ({hooks()})")
check("server:pitato" in out, "...and it says how to start Claude Code")

# the old one again (someone ran an old copy), then --remove: both out
run(OLD, "127.0.0.1:1")
rc, out = run(NEW, "--remove")
s = servers()
check(rc == 0 and "pitato" not in s and "gpi-media" not in s and hooks() == 0, f"--remove: all of it out ({sorted(s)}, {hooks()})")
check(not os.path.exists(LAPTOP + "/.claude/gpi-media") and not os.path.exists(LAPTOP + "/.claude/pitato"), "...the copies too")
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
