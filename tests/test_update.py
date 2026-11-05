"""System > Update software with real git, as a Pi has it: the pitato folder a clone owned by its user (gpitest),
looked at as that user (never as root: nothing of root's left in it). It follows the latest release, not main: what's
pushed to main waits for a release (a version tag here, GitHub's latest release where GitHub's API answers: a pretend
one); a clone of main past the release isn't taken back to it. Update software always at the top of System, saying
New version while there's a newer release (or Finish updating: one got and not put in), Up to date when there isn't;
pressed twice, the update runs as a job of its own (a stand-in systemd-run): on to the release as the folder's owner,
setup.sh --update (a stand-in: as root, no terminal, told who the user is), then a restart (a stand-in systemctl), its
screen saying how it's getting on, nothing else let on the screen meanwhile. Nothing newer: it says it's up to date,
back on System, no restart; a newer release it hadn't looked for yet: put in all the same; no release at all: said.
When it doesn't work (changes here in the way, setup.sh failing, the job gone), System says why, and offers it again.
GitHub's history written afresh (every id new, the same versions: git filter-repo, its tags too): taken as it is, up
to date if it's the same version, put in if there's a newer release, but not over a version of its own here. Pietato
renamed on GitHub: a folder cloned from its old name gets it from the new one once that answers (as the folder's
owner). release.py: the newest version among tags; GitHub's answer, not a pre-release, a draft or a tag it can't
take. In a mount namespace of its own: everything it makes is on a tmpfs at /srv there."""
import http.server, json, os, shutil, subprocess, sys, threading, time

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


CLOCK = [1_760_000_000]


def dated():
    """A commit's date, an hour after the last one's (git's dates go by the second: these never tie)."""
    CLOCK[0] += 3600
    return ["env", f"GIT_AUTHOR_DATE=@{CLOCK[0]} +0000", f"GIT_COMMITTER_DATE=@{CLOCK[0]} +0000"]


def commit(path, text, msg):
    with open(f"{T}/work/{path}", "w") as f:
        f.write(text)
    sh(["git", "-C", T + "/work", "add", "-A"])
    sh(dated() + ["git", "-C", T + "/work", "-c", "user.name=frogCaller", "-c", "user.email=f@example.com", "commit",
                  "-qm", msg])
    sh(["git", "-C", T + "/work", "push", "-q", "origin", "main"])
    return sh(["git", "-C", T + "/work", "rev-parse", "HEAD"]).stdout.strip()


def release(tag, ref="HEAD"):
    """A release on GitHub: its tag, pushed (GitHub makes one for it)."""
    sh(["git", "-C", T + "/work", "tag", "-f", tag, ref])
    sh(["git", "-C", T + "/work", "push", "-q", "--force", "origin", f"refs/tags/{tag}"])
    return sh(["git", "-C", T + "/work", "rev-parse", f"{tag}^{{commit}}"]).stdout.strip()


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
os.makedirs(T + "/work/pitato")
shutil.copy(ROOT + "/pitato/release.py", T + "/work/pitato/release.py")   # (the update asks it for the latest release)
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
release("v1.0")
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
check(f"a newer version on main, not a release yet: still Up to date ({u.new}, {u.release}, {u.words()!r})",
      u.new == 0 and not u.available() and u.release == "v1.0" and u.words() == "Up to date")
release("v1.1-beta")
release("nightly")
u.check()
check(f"...nor with a pre-release's tag, or one that isn't a version ({u.new}, {u.release})",
      u.new == 0 and u.release == "v1.0")
release("v1.1")
u.check()
check(f"a release of it: Update software, New version ({u.new}, {u.release})", u.new == 1 and u.available()
      and u.words() == "New version" and u.release == "v1.1")
check(f"...looked at as the folder's owner: nothing of root's left in it ({not_theirs()[:3]})", not not_theirs())
check("...and the folder itself not changed by looking", read(CLONE + "/README.md") == "# Pitato\n")

# ---- Pietato renamed on GitHub: a folder cloned from its old name gets it from the new one (once that answers) --------
M = g.moved_remote
check("its old name on GitHub, in any form: the new one, in the same form",
      M("https://github.com/frogCaller/pie-tato.git") == "https://github.com/frogCaller/Pietato.git"
      and M("https://github.com/FrogCaller/Pie-Tato/") == "https://github.com/frogCaller/Pietato"
      and M("git@github.com:frogCaller/pie-tato.git") == "git@github.com:frogCaller/Pietato.git"
      and M("ssh://git@github.com/frogCaller/pie-tato") == "ssh://git@github.com/frogCaller/Pietato")
check("...and nothing else: its new name, a fork, somewhere else, a folder",
      not any(M(u) for u in ("https://github.com/frogCaller/Pietato.git", "https://github.com/someone/pie-tato.git",
                             "https://gitlab.com/frogCaller/pie-tato.git", T + "/origin.git", "", None)))
sh(["ln", "-s", T + "/origin.git", T + "/old.git"])                # (GitHub sends the old name on, as it does)
sh(["git", "-C", CLONE, "remote", "set-url", "origin", T + "/old.git"])
origin = lambda: sh(["git", "-C", CLONE, "remote", "get-url", "origin"]).stdout.strip()   # noqa: E731
g.moved_remote = lambda url: T + "/not-yet.git" if url == T + "/old.git" else None
u.check()
check(f"the new name not answering yet: it's left as it was, and it looks all the same ({origin()}, {u.new})",
      origin() == T + "/old.git" and u.new == 1 and u.fetched)
g.moved_remote = lambda url: T + "/origin.git" if url == T + "/old.git" else None
u.check()
check(f"...answering: it gets it from there from now on, looking as before ({origin()}, {u.new}, {u.words()!r})",
      origin() == T + "/origin.git" and u.new == 1 and u.words() == "New version")
check(f"...changed as the folder's owner ({not_theirs()[:3]}), and only once", not not_theirs() and not u.follow_rename())
g.moved_remote = M

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
check("A again: updating, its screen up", m.view == "update" and "Updating Pietato" in drawn())
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
      "Updating Pietato" in seen and not [x for x in seen if any(w in x for w in ("nstall", "Getting", "Leave"))])
check(f"...dots under it, lit one after another, just they drawn again on each step ({sorted(lit)}, {len(looks)} "
      f"looks, {FB.parts[:1]})", lit == {0, 1, 2} and len(looks) >= 3 and FB.parts
      and all((b[2] - b[0]) * (b[3] - b[1]) < 100 * 40 for b in FB.parts))
m.press("b"); m.press("home")
r = m.web_command({"cmd": "open", "app": "Home"})
check(f"...nothing to press meanwhile, nor anything from the web page put on the screen ({r})",
      m.view == "update" and "error" in r)
check("...then it restarts the Pi", until(lambda: "reboot" in read(T + "/reboot.log"), 20))
check(f"...after it's on to the release, as the folder's owner (now {second[:7]}; nothing of root's: "
      f"{not_theirs()[:3]}), still on its branch", sh(["git", "-C", CLONE, "rev-parse", "HEAD"]).stdout.strip() == second
      and not not_theirs() and "Now with updates." in read(CLONE + "/README.md")
      and sh(["git", "-C", CLONE, "branch", "--show-current"]).stdout.strip() == "main"
      and "==> The latest release: v1.1" in read(T + "/update.log"))
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
check(f"...its screen: just Updating Pietato, whether or not there's anything newer ({look})",
      "Updating Pietato" in look and not [t for t in look if "Getting" in t or "newer" in t])
ok = until(lambda: m.view == "list" and m.msg == "Pietato is up to date", 20)
check(f"...nothing newer: back to System, up to date ({m.msg!r})", ok and m.tab == si)
time.sleep(0.5)
check("...looking was all: nothing put in, no restart", "systemd-run" in read(T + "/calls.log")
      and not os.path.exists(T + "/setup.called") and not os.path.exists(T + "/reboot.log")
      and "v1.1 is here already" in read(T + "/update.log") and "Already up to date" in read(T + "/update.log"))

# ---- a newer release it hadn't looked for yet: pressed, it's got and put in all the same --------------------------------
pushed = commit("README.md", "# Pitato\n\nNot looked for yet.\n", "Not looked for")
release("v1.2")
check(f"a newer release on GitHub, not looked for yet ({u.words()!r})", not u.available())
m.view, m.tab = "list", si
m.load_tab(si)
m.sels[si] = 0
m.press("a"); m.press("a")
check("pressed: updating", m.view == "update")
check("...got, put in, and the Pi restarts", until(lambda: "reboot" in read(T + "/reboot.log"), 25)
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
release("v1.3")
open(CLONE + "/README.md", "a").write("my own line\n")                    # (changed here, by hand)
shutil.chown(CLONE + "/README.md", USER, USER)
u.check()
check("a newer version again", u.available() and u.words() == "New version")
check("pressed: updating", start_update())
ok = back_with("files in the Pietato folder were changed here")
check(f"...git won't: back to System, saying why ({m.msg!r})", ok)
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
check(f"...got but not put in: Update software says Finish updating ({u.new}, {u.behind})",
      u.new == 0 and u.behind and u.words() == "Finish updating"
      and until(lambda: m.row_right(m.tab_items(si)[0])[0] == "Finish updating", 5))
os.remove(T + "/setup.result")
check("...pressed again: put in, and the Pi restarts", start_update()
      and until(lambda: "reboot" in read(T + "/reboot.log"), 25) and read(T + "/installed-commit").strip() == third)

# ---- GitHub's history written afresh (a line taken out of its notes): the same versions, every id new ------------------
def rewrite(old, new):
    """GitHub's history written afresh, as git filter-repo does it: a word changed in a note, so every id from there on
    is new, every version's files the same, the releases' tags moved with them; pushed over GitHub's."""
    sh(["git", "-C", T + "/work", "filter-repo", "--force", "--quiet", "--message-callback",
        f"return message.replace({old.encode()!r}, {new.encode()!r})"])
    sh(["git", "-C", T + "/work", "remote", "add", "origin", T + "/origin.git"])     # (filter-repo takes it away)
    sh(["git", "-C", T + "/work", "push", "-q", "--force", "origin", "main"])
    sh(["git", "-C", T + "/work", "push", "-q", "--force", "--tags", "origin"])
    return sh(["git", "-C", T + "/work", "rev-parse", "HEAD"]).stdout.strip()


def here():
    return sh(["git", "-C", CLONE, "rev-parse", "HEAD"]).stdout.strip()


def tree(where, ref="HEAD"):
    return sh(["git", "-C", where, "rev-parse", ref + "^{tree}"]).stdout.strip()


u = g.Updater(folder=CLONE)                     # (after the restart: a new media mode's)
m.updater = u
u.on_change = m.update_found
afresh = rewrite("Pitato", "Pietato")
check(f"GitHub's history written afresh, its releases with it: every id new, the same files ({third[:7]}, now "
      f"{afresh[:7]})", afresh != third and tree(T + "/work") == tree(CLONE) and here() == third
      and sh(["git", "-C", T + "/work", "rev-parse", "v1.3^{commit}"]).stdout.strip() == afresh)
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
fourth = rewrite("Pietato", "Pietato, again")     # (pushed, then written afresh)
release("v1.4", fourth)
u.check()
check(f"a newer release, the history written afresh again: just the one newer ({u.new}, {u.words()!r})",
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
sh(dated() + ["git", "-C", CLONE, "-c", "user.name=me", "-c", "user.email=me@example.com", "commit", "-qam", "Mine"])
mine = here()
rewrite("again", "once more")
u.check()
check(f"a version of its own here, newer than the latest release (GitHub's history written afresh since): nothing "
      f"newer to go on to, it's its own to put in ({u.new}, {u.behind}, {u.words()!r})",
      u.new == 0 and u.behind and u.words() == "Finish updating")
fifth = commit("README.md", "# Pitato\n\nA fifth.\n", "Fifth")
release("v1.5")
u.check()
check(f"...then a newer release: there's a version on GitHub ({u.new}, {u.words()!r})", u.available() and u.new > 0
      and u.words() == "New version")
check("pressed: updating", start_update())
ok = back_with("changes of its own")
check(f"...git won't, and GitHub's isn't taken over it: back to System, saying why ({m.msg!r})", ok)
check("...its own version kept, nothing put in, no restart", here() == mine and "my own version" in read(CLONE + "/README.md")
      and not os.path.exists(T + "/setup.called") and not os.path.exists(T + "/reboot.log"))
sh(["git", "-C", CLONE, "fetch", "-q", "--force", "origin", "+refs/tags/v1.4:refs/tags/v1.4"])
sh(["git", "-C", CLONE, "reset", "-q", "--hard", "v1.4"])
u.check()
check(f"put on GitHub's new history by hand (git reset to v1.4): the files put in, under a new id: not Finish "
      f"updating, and v1.5 one newer ({u.new}, {u.behind}, {u.words()!r})", here() != fourth
      and tree(CLONE) == tree(CLONE, fourth) and u.new == 1 and not u.behind and u.words() == "New version")

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

# ---- release.py: the newest version among tags; GitHub's answer for its latest release ---------------------------------
import pitato.release as R  # noqa: E402
check(f"the newest version among tags: v1.10 after v1.9, not a pre-release or a tag that isn't a version "
      f"({R.newest(['a' + chr(9) + 'refs/tags/v1.9', 'b' + chr(9) + 'refs/tags/v1.10', 'v1.2.3', 'v2.0-rc1', 'nightly'])})",
      R.newest(["a\trefs/tags/v1.9", "b\trefs/tags/v1.10", "v1.2.3", "v2.0-rc1", "nightly", "v1..2"]) == "v1.10"
      and R.newest(["v0.9", "1.0"]) == "1.0" and R.newest(["nightly", "latest"]) is None and R.newest([]) is None)


class API(http.server.BaseHTTPRequestHandler):
    """A pretend GitHub API: its answer for the latest release (what it's set to), and what it was asked."""
    answer = (200, {"tag_name": "v1.5", "prerelease": False, "draft": False})
    asked = []

    def do_GET(self):
        API.asked.append((self.path, self.headers.get("User-Agent"), self.headers.get("Accept")))
        code, body = API.answer
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), API)
threading.Thread(target=api.serve_forever, daemon=True).start()
os.environ["PITATO_RELEASES_API"] = f"http://127.0.0.1:{api.server_port}/repos/{{repo}}/releases/latest"
said = {}
for name, answer in (("latest", (200, {"tag_name": "v1.5", "prerelease": False, "draft": False})),
                     ("pre", (200, {"tag_name": "v1.6", "prerelease": True, "draft": False})),
                     ("draft", (200, {"tag_name": "v1.6", "prerelease": False, "draft": True})),
                     ("none", (404, {"message": "Not Found"})), ("limit", (403, {"message": "API rate limit exceeded"})),
                     ("junk", (200, b"<html>not json</html>")), ("odd", (200, {"tag_name": "v1.5; rm -rf ~"})),
                     ("number", (200, {"tag_name": 15}))):
    API.answer = answer
    said[name] = R.from_github("frogCaller/Pietato", timeout=5)
check(f"GitHub's latest release: its tag; not a pre-release or a draft; none, a refusal, junk or an odd tag: none ({said})",
      said == {"latest": "v1.5", "pre": None, "draft": None, "none": None, "limit": None, "junk": None, "odd": None,
               "number": None})
check(f"...asked for the folder's repository, as Pietato, for JSON ({API.asked[0]})",
      API.asked[0] == ("/repos/frogCaller/Pietato/releases/latest", "Pietato-update", "application/vnd.github+json"))
API.asked.clear()
check("...nothing asked for an address that isn't GitHub's owner/name",
      R.from_github("", 5) is None and R.from_github("not a repo", 5) is None and not API.asked)
API.answer = (500, {"message": "down"})
check("...GitHub's API not answering: the newest version tag (and its answer first when it does)",
      R.latest("frogCaller/Pietato", ["v1.2", "v1.3"], timeout=5) == "v1.3"
      and (setattr(API, "answer", (200, {"tag_name": "v1.2"})) or R.latest("frogCaller/Pietato", ["v1.3"], 5) == "v1.2"))
os.environ["PITATO_RELEASES_API"] = "http://127.0.0.1:9/repos/{repo}/releases/latest"
check("...nor there at all: the tags' all the same", R.latest("frogCaller/Pietato", ["v1.3"], timeout=5) == "v1.3")
os.environ["PITATO_RELEASES_API"] = f"http://127.0.0.1:{api.server_port}/repos/{{repo}}/releases/latest"

# ---- Update software, asking GitHub's API (a folder from GitHub): its latest release, not a newer tag's -------------------
real_repo = g.github_repo
g.github_repo = lambda url: "frogCaller/Pietato" if url else None     # (this pretend GitHub's folder, as GitHub's)
sixth = commit("README.md", "# Pitato\n\nA sixth.\n", "Sixth")
release("v1.6")                                    # (on GitHub, a pre-release: its API says v1.5's the latest)
API.answer = (200, {"tag_name": "v1.5", "prerelease": False, "draft": False})
API.asked.clear()
u = g.Updater(folder=CLONE)
m.updater = u
u.on_change = m.update_found
u.check()
check(f"GitHub's latest release followed, not the newest tag: v1.5, one newer ({u.release}, {u.new}, {API.asked[:1]})",
      u.release == "v1.5" and u.new == 1 and API.asked and API.asked[0][0] == "/repos/frogCaller/Pietato/releases/latest")
API.answer = (200, {"tag_name": "v1.6", "prerelease": False, "draft": False})
u.check()
check(f"...v1.6 the latest now: two newer ({u.release}, {u.new})", u.release == "v1.6" and u.new == 2)
API.asked.clear()
check("pressed: updating", start_update())
check(f"...the update asked GitHub too, went on to v1.6, put it in, and the Pi restarts ({here()[:7]})",
      until(lambda: "reboot" in read(T + "/reboot.log"), 25) and here() == sixth
      and read(T + "/installed-commit").strip() == sixth and API.asked
      and "==> The latest release: v1.6" in read(T + "/update.log"))
API.answer = (500, {"message": "down"})
u = g.Updater(folder=CLONE)
u.check()
check(f"GitHub's API not answering: the newest version tag, and that's here: Up to date ({u.release}, {u.words()!r})",
      u.release == "v1.6" and u.new == 0 and u.words() == "Up to date")
API.answer = (200, {"tag_name": "v1.6", "prerelease": False, "draft": False})

# ---- a clone of main, newer than the latest release: not taken back to it ---------------------------------------------
commit("README.md", "# Pitato\n\nA seventh, on main.\n", "Seventh")
sh(["git", "clone", "-q", T + "/origin.git", HOME + "/main-clone"])
um = g.Updater(folder=HOME + "/main-clone")
um.check()
check(f"a clone of main, newer than the latest release: nothing newer, not taken back to it ({um.release}, {um.new})",
      um.release == "v1.6" and um.new == 0 and um.fetched)

# ---- no release at all (a fork with none): said, and nothing to update to -------------------------------------------
sh(["git", "init", "-q", "--bare", "-b", "main", T + "/norel.git"])
sh(["git", "-C", T + "/work", "push", "-q", T + "/norel.git", "main"])      # (main, and no tags)
sh(["git", "clone", "-q", T + "/norel.git", HOME + "/norel"])
API.answer = (404, {"message": "Not Found"})
open(T + "/installed-commit", "w").write(sh(["git", "-C", HOME + "/norel", "rev-parse", "HEAD"]).stdout)   # (put in, as setup.sh does)
un = g.Updater(folder=HOME + "/norel")
un.check()
check(f"no release, nor a version tag: No release yet ({un.words()!r}, {un.new})",
      un.words() == "No release yet" and un.new == 0 and not un.fetched and not un.available())
for f in ("setup.called", "reboot.log"):
    if os.path.exists(f"{T}/{f}"):
        os.remove(f"{T}/{f}")
until(lambda: not os.path.exists(T + "/unit.running"), 15)     # (the last update's job over)
err = un.begin()
ok = err is None and until(lambda: read(g.UPDATE_STATUS).startswith("failed"), 15)
state, why = un.progress()
check(f"...pressed: it says so, nothing put in, no restart ({err}, {state}, {why!r})",
      ok and state == "failed" and "no release" in why and not os.path.exists(T + "/setup.called")
      and not os.path.exists(T + "/reboot.log") and "No release to update to" in read(T + "/update.log"))
un.done()
g.github_repo = real_repo
API.answer = (200, {"tag_name": "v1.6", "prerelease": False, "draft": False})
api.shutdown()
os.environ.pop("PITATO_RELEASES_API", None)

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
      and "changes of its own" in W("failed pull fatal: Not possible to fast-forward to v1.5: this folder's history "
                                    "diverges from it")
      and "no release" in W("failed release")
      and W("failed install").startswith("The update didn't finish"))

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
