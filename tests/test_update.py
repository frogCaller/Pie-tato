"""System > Update software with real git, as a Pi has it: the pitato folder a clone owned by its user (gpitest),
looked at as that user (never as root: nothing of root's left in it); Update software always at the top of System,
saying New version while there's a newer one (or Finish updating: one pulled and not put in), Up to date when there
isn't; pressed twice, the update runs as a job of its own (a stand-in systemd-run): git pull as the folder's owner,
setup.sh --update (a stand-in: as root, no terminal, told who the user is), then a restart (a stand-in systemctl), its
screen saying how it's getting on, nothing else let on the screen meanwhile. Nothing newer: git pull, and it says it's
up to date, back on System, no restart; a newer version it hadn't looked for yet: put in all the same. When it doesn't
work (changes here in the way, setup.sh failing, the job gone), System says why, and offers it again. GitHub's
history written afresh (every id new, the same versions: git filter-repo): taken as it is, up to date if it's the same
version, put in if there's a newer one, but not over a version of its own here. In a mount namespace of its own:
everything it makes is on a tmpfs at /srv there."""
import json, os, shutil, subprocess, sys, time

from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
if os.environ.get("UPD_NS") != "1":
    os.execvpe("unshare", ["unshare", "-m", sys.executable, os.path.abspath(__file__)], dict(os.environ, UPD_NS="1"))
subprocess.run(["mount", "--make-rprivate", "/"], check=True)
subprocess.run(["mount", "-t", "tmpfs", "-o", "mode=755", "tmpfs", "/srv"], check=True)

sys.path.insert(0, TESTS)
import pietato_all as g  # noqa: E402
from PIL import ImageDraw  # noqa: E402

T, USER = "/srv/upd", "gpitest"
HOME = T + "/home"
CLONE = HOME + "/pitato"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def sh(cmd, user=USER, cwd=None, ok=True):
    """A command as the folder's owner (or root)."""
    pre = ["runuser", "-u", user, "--", "env", f"HOME={HOME}"] if user != "root" else []
    r = subprocess.run(pre + cmd, cwd=cwd, capture_output=True, text=True)
    if ok and r.returncode != 0:
        raise SystemExit(f"{cmd}: {r.stderr}")
    return r


def commit(path, text, msg):
    with open(f"{T}/work/{path}", "w") as f:
        f.write(text)
    sh(["git", "-C", T + "/work", "add", "-A"])
    sh(["git", "-C", T + "/work", "-c", "user.name=frogCaller", "-c", "user.email=f@example.com", "commit", "-qm", msg])
    sh(["git", "-C", T + "/work", "push", "-q", "origin", "main"])
    return sh(["git", "-C", T + "/work", "rev-parse", "HEAD"]).stdout.strip()


def not_theirs():
    return subprocess.run(["find", CLONE, "!", "-user", USER], capture_output=True, text=True).stdout.split()


def read(path):
    try:
        return open(path).read()
    except OSError:
        return ""


# ---- a GitHub, and a Pi's pitato folder cloned from it ---------------------------------------------------------------
os.makedirs(T + "/bin")
os.makedirs(HOME)
shutil.chown(T, USER, USER)
shutil.chown(HOME, USER, USER)
sh(["git", "init", "-q", "--bare", "-b", "main", T + "/origin.git"])
sh(["git", "clone", "-q", T + "/origin.git", T + "/work"], ok=False)    # (empty: it says so)
os.makedirs(T + "/work/static/fonts")
open(T + "/work/static/fonts/OFL.txt", "w").write("fonts\n")
open(T + "/work/setup.sh", "w").write(f"""#!/bin/bash
# stand-in setup.sh: what it was asked, as whom; then it notes what it put in, as the real one does
HERE="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
{{ echo "args=$*"; echo "uid=$(id -u)"; echo "sudo_user=$SUDO_USER"; echo "tty=$([ -t 0 ] && echo yes || echo no)"
   echo "debian=$DEBIAN_FRONTEND"; }} > {T}/setup.called
echo "==> Installing packages"
sleep 1.2
echo "==> Installing the controller and media script"
sleep 1.2
if [ "$(cat {T}/setup.result 2>/dev/null)" = fail ]; then echo "E: pretend trouble"; exit 1; fi
git -c safe.directory='*' -C "$HERE" rev-parse HEAD > {T}/installed-commit
""")
for name, body in {
    "systemd-run": f"""#!/bin/bash
# stand-in systemd-run: the job in the background, on its own, as a unit would be (one at a time)
echo "systemd-run $*" >> {T}/calls.log
while [[ "$1" == --* ]]; do shift; done
if [ -e {T}/unit.running ]; then
  echo "Failed to start transient service unit: Unit pitato-update.service was already loaded or has a fragment file." >&2
  exit 1
fi
touch {T}/unit.running
( "$@"; rm -f {T}/unit.running ) > /dev/null 2>&1 &
""",
    "systemctl": f"""#!/bin/bash
echo "systemctl $*" >> {T}/calls.log
case "$1" in
  is-active) [ -e {T}/unit.running ] && exit 0 || exit 3 ;;
  reboot) echo reboot >> {T}/reboot.log ;;
esac
exit 0
"""}.items():
    open(f"{T}/bin/{name}", "w").write(body)
    os.chmod(f"{T}/bin/{name}", 0o755)
first = commit("README.md", "# Pitato\n", "Pitato")
sh(["git", "clone", "-q", T + "/origin.git", CLONE])
os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
g.UPDATE_RUN, g.UPDATE_SCRIPT, g.UPDATE_STATUS = T + "/run", T + "/run/update.sh", T + "/run/update.status"
g.UPDATE_LOG, g.INSTALLED, g.UPDATE_GRACE = T + "/update.log", T + "/installed-commit", 3

# ---- looking for a newer version, as the folder's owner --------------------------------------------------------------
u = g.Updater(folder=CLONE)
u.check()
check(f"nothing newer: Update software there all the same, Up to date ({u.new}, {u.behind}, {u.words()!r})",
      u.new == 0 and not u.behind and not u.available() and u.shown() and u.words() == "Up to date")
second = commit("README.md", "# Pitato\n\nNow with updates.\n", "Update software")
u.check()
check(f"a newer version on GitHub: Update software, New version ({u.new})", u.new == 1 and u.available()
      and u.words() == "New version")
check(f"...looked at as the folder's owner: nothing of root's left in it ({not_theirs()[:3]})", not not_theirs())
check("...and the folder itself not changed by looking", read(CLONE + "/README.md") == "# Pitato\n")

saved_static = g.STATIC
g.STATIC = T + "/nowhere/static"
check("a pitato folder that isn't a git clone (a zip, say): it doesn't look, and can't update",
      g.update_folder() is None and g.Updater().folder is None and not g.Updater().available()
      and not g.Updater().shown() and "git clone" in g.Updater().begin())
g.STATIC = CLONE + "/static"
check("...one that is: found from the static folder the service is told about", g.update_folder() == CLONE)
g.STATIC = saved_static

# ---- System, on the Pi's screen ---------------------------------------------------------------------------------------
S = T + "/media"
os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: S + "/home/u"
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; parts = []
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy(); FB.parts.append(box)
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]


def drawn():
    texts.clear(); m.dirty = True; m.flush()
    return list(texts)


def until(cond, secs=20.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        m.tick()
        if m.dirty:
            m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return cond()


m = g.Media()
m.enter()
m.set_setting("sys_view", "List")              # (System's list, where Update software is: SELECT on its dashboard)
m.updater = u
u.on_change = m.update_found
si = m.tab_index("system")
m.open_app(si)
rows = m.tab_items(si)
check(f"System: Update software at the top, New version on its right ({rows[0]['title']!r}, "
      f"{m.row_right(rows[0])[:2]})", rows[0]["title"] == "Update software" and rows[0]["src"] == "update"
      and m.row_right(rows[0])[:2] == ("New version", g.ACCENT) and rows[-1]["title"] == "Shut down")
check("...on the screen", {"Update software", "New version"} <= set(drawn()))
m.sels[si] = 0
m.press("a")
check(f"A once: asked again, and told what it does ({m.msg!r})", m.confirm[0] == "update" and m.view == "list"
      and "press A again" in drawn() and "The Pi restarts when it's done" in str(m.msg))
for f in ("setup.called", "reboot.log", "calls.log"):
    if os.path.exists(f"{T}/{f}"):
        os.remove(f"{T}/{f}")
m.press("a")
check("A again: updating, its screen up", m.view == "update" and "Updating Pie-tato" in drawn())
check(f"...as a job of its own ({[l for l in read(T + '/calls.log').splitlines() if 'systemd-run' in l][:1]})",
      "systemd-run --quiet --collect --unit=pitato-update" in read(T + "/calls.log"))
seen, lit, looks = set(), set(), set()
FB.parts.clear()


def watching():
    """Its screen, as the main loop draws it (a whole picture now and then, just its dots on each step)."""
    m.tick()
    m.flush()
    seen.update(texts)
    texts.clear()
    lit.add(m.update_frame % 3)
    if FB.last is not None:
        looks.add(FB.last.crop((270, 250, 370, 290)).tobytes())
    return "==> Installing the controller and media script" in read(T + "/update.log")


until(watching, 20)
f0, t0 = m.update_frame, time.monotonic()
while time.monotonic() - t0 < 1.4:                   # (the main loop wakes for each step: here, often)
    m.tick()
    time.sleep(0.005)
steps = m.update_frame - f0
check(f"...its dots a step every {1.4 / max(steps, 1):.2f} s ({steps} in 1.4 s), half again as quick as the 0.35 s "
      f"they were", m.view == "update" and 5 <= steps <= 7)
end = time.monotonic() + 1.2
while time.monotonic() < end:
    watching()
    time.sleep(0.05)
check(f"...its screen just says it's updating, and none of what it's doing ({sorted(seen)})",
      "Updating Pie-tato" in seen and not [x for x in seen if any(w in x for w in ("nstall", "Getting", "Leave"))])
check(f"...dots under it, lit one after another, just they drawn again on each step ({sorted(lit)}, {len(looks)} "
      f"looks, {FB.parts[:1]})", lit == {0, 1, 2} and len(looks) >= 3 and FB.parts
      and all((b[2] - b[0]) * (b[3] - b[1]) < 100 * 40 for b in FB.parts))
m.press("b"); m.press("home")
r = m.web_command({"cmd": "open", "app": "Home"})
check(f"...nothing to press meanwhile, nor anything from the web page put on the screen ({r})",
      m.view == "update" and "error" in r)
check("...then it restarts the Pi", until(lambda: "reboot" in read(T + "/reboot.log"), 20))
check(f"...after git pull, as the folder's owner (now {second[:7]}; nothing of root's: {not_theirs()[:3]})",
      sh(["git", "-C", CLONE, "rev-parse", "HEAD"]).stdout.strip() == second and not not_theirs()
      and "Now with updates." in read(CLONE + "/README.md"))
called = dict(line.split("=", 1) for line in read(T + "/setup.called").split())
check(f"...and setup.sh --update, as root, no terminal, told who the user is ({called})",
      called == {"args": "--update", "uid": "0", "sudo_user": USER, "tty": "no", "debian": "noninteractive"})
check("...which noted what it put in", read(T + "/installed-commit").strip() == second)
check("...its log kept", "==> Installing packages" in read(T + "/update.log") and "Pietato update" in read(T + "/update.log"))
u2 = g.Updater(folder=CLONE)
u2.check()
check(f"after the restart: nothing newer, Up to date ({u2.words()!r})", not u2.available() and u2.words() == "Up to date")
m.updater = u = u2
u.on_change = m.update_found


# ---- pressed with nothing newer: git pull, up to date, back to System, no restart -------------------------------------
for f in ("setup.called", "reboot.log", "calls.log"):
    if os.path.exists(f"{T}/{f}"):
        os.remove(f"{T}/{f}")
m.view, m.tab = "list", si
m.load_tab(si)
rows = m.tab_items(si)
check(f"System: Update software at the top all the same, Up to date on it, not lit ({m.row_right(rows[0])[:2]})",
      rows[0]["title"] == "Update software" and m.row_right(rows[0])[:2] == ("Up to date", g.MUTED))
m.sels[si] = 0
m.press("a")
check(f"A once: what it does ({m.msg!r})", m.confirm[0] == "update"
      and m.msg == "Press A again to get the newest version. If there is one, the Pi restarts")
m.press("a")
check("A again: updating", m.view == "update")
look = drawn()
check(f"...its screen: just Updating Pie-tato, whether or not there's anything newer ({look})",
      "Updating Pie-tato" in look and not [t for t in look if "Getting" in t or "newer" in t])
ok = until(lambda: m.view == "list" and m.msg == "Pietato is up to date", 20)
check(f"...nothing newer: back to System, up to date ({m.msg!r})", ok and m.tab == si)
time.sleep(0.5)
check("...git pull was all: nothing put in, no restart", "systemd-run" in read(T + "/calls.log")
      and not os.path.exists(T + "/setup.called") and not os.path.exists(T + "/reboot.log")
      and "Already up to date" in read(T + "/update.log"))

# ---- a newer version it hadn't looked for yet: pressed, it's pulled and put in all the same ------------------------------
pushed = commit("README.md", "# Pitato\n\nNot looked for yet.\n", "Not looked for")
check(f"a newer version on GitHub, not looked for yet ({u.words()!r})", not u.available())
m.view, m.tab = "list", si
m.load_tab(si)
m.sels[si] = 0
m.press("a"); m.press("a")
check("pressed: updating", m.view == "update")
check("...pulled, put in, and the Pi restarts", until(lambda: "reboot" in read(T + "/reboot.log"), 25)
      and read(T + "/installed-commit").strip() == pushed and os.path.exists(T + "/setup.called"))
u = g.Updater(folder=CLONE)                     # (after the restart: a new media mode's)
u.check()
m.updater = u
u.on_change = m.update_found


def start_update():
    for f in ("setup.called", "reboot.log"):
        if os.path.exists(f"{T}/{f}"):
            os.remove(f"{T}/{f}")
    m.view, m.tab = "list", si
    m.load_tab(si)
    m.sels[si] = 0
    m.press("a"); m.press("a")
    return m.view == "update"


def back_with(words, secs=25):
    return until(lambda: m.view == "list" and words in str(m.msg), secs)


# ---- it doesn't work: changes here in the way ---------------------------------------------------------------------
third = commit("README.md", "# Pitato\n\nA third.\n", "Third")
open(CLONE + "/README.md", "a").write("my own line\n")                    # (changed here, by hand)
shutil.chown(CLONE + "/README.md", USER, USER)
u.check()
check("a newer version again", u.available() and u.words() == "New version")
check("pressed: updating", start_update())
ok = back_with("files in the Pietato folder were changed here")
check(f"...git pull won't: back to System, saying why ({m.msg!r})", ok)
check("...nothing put in, no restart", not os.path.exists(T + "/setup.called") and not os.path.exists(T + "/reboot.log"))
check("...the change here kept, Update software still there", "my own line" in read(CLONE + "/README.md")
      and until(lambda: m.tab_items(si)[0]["title"] == "Update software", 10))
sh(["git", "-C", CLONE, "checkout", "--", "README.md"])

# ---- it doesn't work: setup.sh fails --------------------------------------------------------------------------------
open(T + "/setup.result", "w").write("fail")
check("setup.sh failing: pressed, updating", start_update())
ok = back_with("didn't finish putting it in")
check(f"...back to System, saying so ({m.msg!r})", ok)
check("...no restart", not os.path.exists(T + "/reboot.log"))
u.check()
check(f"...pulled but not put in: Update software says Finish updating ({u.new}, {u.behind})",
      u.new == 0 and u.behind and u.words() == "Finish updating"
      and until(lambda: m.row_right(m.tab_items(si)[0])[0] == "Finish updating", 5))
os.remove(T + "/setup.result")
check("...pressed again: put in, and the Pi restarts", start_update()
      and until(lambda: "reboot" in read(T + "/reboot.log"), 25) and read(T + "/installed-commit").strip() == third)

# ---- GitHub's history written afresh (a line taken out of its notes): the same versions, every id new ------------------
def rewrite(old, new):
    """GitHub's history written afresh, as git filter-repo does it: a word changed in a note, so every id from there on
    is new, every version's files the same; pushed over GitHub's (as the push script does)."""
    sh(["git", "-C", T + "/work", "filter-repo", "--force", "--quiet", "--message-callback",
        f"return message.replace({old.encode()!r}, {new.encode()!r})"])
    sh(["git", "-C", T + "/work", "remote", "add", "origin", T + "/origin.git"])     # (filter-repo takes it away)
    sh(["git", "-C", T + "/work", "push", "-q", "--force", "origin", "main"])
    return sh(["git", "-C", T + "/work", "rev-parse", "HEAD"]).stdout.strip()


def here():
    return sh(["git", "-C", CLONE, "rev-parse", "HEAD"]).stdout.strip()


def tree(where, ref="HEAD"):
    return sh(["git", "-C", where, "rev-parse", ref + "^{tree}"]).stdout.strip()


u = g.Updater(folder=CLONE)                     # (after the restart: a new media mode's)
m.updater = u
u.on_change = m.update_found
afresh = rewrite("Pitato", "Pietato")
check(f"GitHub's history written afresh: every id new, the same files ({third[:7]}, now {afresh[:7]})",
      afresh != third and tree(T + "/work") == tree(CLONE) and here() == third)
u.check()
check(f"...nothing newer for all that: Up to date ({u.new}, {u.behind}, {u.words()!r})",
      u.new == 0 and not u.behind and u.words() == "Up to date")
check("pressed all the same: updating", start_update())
ok = until(lambda: m.view == "list" and m.msg == "Pietato is up to date", 25)
check(f"...GitHub's history taken as it is, the same version: up to date, back to System ({m.msg!r})", ok)
time.sleep(0.5)
check(f"...the folder on GitHub's new history ({here()[:7]}), its new id noted, nothing put in, no restart",
      here() == afresh and read(T + "/installed-commit").strip() == afresh and not os.path.exists(T + "/setup.called")
      and not os.path.exists(T + "/reboot.log") and "written afresh" in read(T + "/update.log"))
commit("README.md", "# Pitato\n\nA fourth.\n", "Fourth")
fourth = rewrite("Pietato", "Pietato, again")     # (pushed, then written afresh: the push script's way)
u.check()
check(f"a newer version, the history written afresh again: just the one newer ({u.new}, {u.words()!r})",
      u.new == 1 and u.words() == "New version")
check("pressed: updating", start_update())
check(f"...GitHub's history taken, the new version put in, and the Pi restarts ({here()[:7]})",
      until(lambda: "reboot" in read(T + "/reboot.log"), 25) and here() == fourth
      and read(T + "/installed-commit").strip() == fourth and "A fourth." in read(CLONE + "/README.md"))
u = g.Updater(folder=CLONE)                     # (after the restart)
m.updater = u
u.on_change = m.update_found
open(CLONE + "/README.md", "a").write("my own version\n")
shutil.chown(CLONE + "/README.md", USER, USER)
sh(["git", "-C", CLONE, "-c", "user.name=me", "-c", "user.email=me@example.com", "commit", "-qam", "Mine"])
mine = here()
rewrite("again", "once more")
u.check()
check(f"a version of its own here, GitHub's history written afresh: there's a version on GitHub ({u.words()!r})",
      u.available())
check("pressed: updating", start_update())
ok = back_with("changes of its own")
check(f"...git pull won't, and GitHub's isn't taken over it: back to System, saying why ({m.msg!r})", ok)
check("...its own version kept, nothing put in, no restart", here() == mine and "my own version" in read(CLONE + "/README.md")
      and not os.path.exists(T + "/setup.called") and not os.path.exists(T + "/reboot.log"))
sh(["git", "-C", CLONE, "reset", "-q", "--hard", "@{upstream}"])
u.check()
check(f"put on GitHub's new history by hand (git reset): the files put in, under a new id: Up to date, not Finish "
      f"updating ({u.new}, {u.behind}, {u.words()!r})", here() != fourth and tree(CLONE) == tree(CLONE, fourth)
      and u.new == 0 and not u.behind and u.words() == "Up to date")

# ---- the job: one at a time; gone without a word; taken up again -----------------------------------------------------
open(T + "/unit.running", "w").close()
u3 = g.Updater(folder=CLONE)
check(f"an update running already: not started twice ({u3.begin()!r})", u3.begin() == "It's updating already")
os.makedirs(T + "/run", exist_ok=True)
open(g.UPDATE_STATUS, "w").write("install\n")
check("media mode restarted while it updates: it takes its screen up again", g.Updater(folder=CLONE).under_way())
m2 = g.Media()
check("...from the start", m2.view == "update")
os.remove(T + "/unit.running")
u4 = g.Updater(folder=CLONE)
u4.started = time.monotonic() - 10
state, why = u4.progress()
check(f"the job gone without a word: it stopped ({state}, {why!r})", state == "failed" and "stopped" in why)
open(g.UPDATE_STATUS, "w").write("failed install\n")
check("an update that didn't work, from before: not taken up", not g.Updater(folder=CLONE).under_way())

# ---- git's words, as System says them ----------------------------------------------------------------------------------
W = g.update_why
check("why, in words", "GitHub didn't answer" in W("failed pull fatal: unable to access 'https://github.com/x/y/': "
                                                    "Could not resolve host: github.com")
      and "GitHub didn't answer" in W("failed pull ssh: connect to host github.com port 22: Connection timed out "
                                      "fatal: Could not read from remote repository.")
      and "changes of its own" in W("failed pull hint: Diverging branches can't be fast-forwarded fatal: Not "
                                    "possible to fast-forward, aborting.")
      and "changed here" in W("failed pull error: Your local changes to the following files would be overwritten "
                              "by merge: README.md Please commit your changes or stash them before you merge. Aborting")
      and W("failed install").startswith("The update didn't finish"))

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
