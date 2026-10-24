"""System > Update software: a newer Pitato where it came from, and putting it in.

The pitato folder is a git clone (git clone, then sudo bash setup.sh). Now and then it's asked, as the folder's owner
(git fetch: never as root, which would leave files in it that git pull couldn't change), whether there's anything
newer; System shows Update software only while there is. That runs git pull, then setup.sh --update (no questions:
it keeps how it was set up), then restarts the Pi, as a job of its own (systemd-run), so setup.sh putting in a new
media mode can't stop it partway. setup.sh notes what it put in: an update that got no further than git pull is
offered again, to finish."""
import os
import pwd
import shlex
import shutil
import subprocess
import threading
import time

from .config import STATE_FILE, STATIC

UPDATE_FIRST = 120          # seconds after it starts that it first looks (the network's up by then)
UPDATE_EVERY = 6 * 3600     # ...and then between looks
UPDATE_STALE = 600          # System opened: it looks again if it last looked longer ago than this
UPDATE_GRACE = 8            # seconds an update may seem stopped (it's just starting) before that's believed
UPDATE_RUN = "/run/pitato"  # the update's script, and how it's getting on (gone once the Pi restarts)
UPDATE_SCRIPT = UPDATE_RUN + "/update.sh"
UPDATE_STATUS = UPDATE_RUN + "/update.status"
UPDATE_LOG = "/var/log/pitato-update.log"
UPDATE_UNIT = "pitato-update"
INSTALLED = os.path.join(os.path.dirname(STATE_FILE), "installed-commit")   # what setup.sh last put in (git's id)
GIT_QUIET = {"GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=20",
             "LC_ALL": "C"}    # (a question from git or ssh would wait for ever, unseen: an error instead)
UPDATE_SH = """#!/bin/bash
# Pitato's update, from System > Update software (pitato/update.py wrote this): the pitato folder brought up to date
# by git pull, as its owner; then setup.sh --update puts it in, and the Pi restarts.
DIR="$1" OWNER="$2"
STATUS={status}
exec > {log} 2>&1
say() {{ printf '%s\\n' "$1" > "$STATUS.tmp" && mv -f "$STATUS.tmp" "$STATUS"; }}
echo "Pitato update, $(date)"
say pull
HOME_DIR="$(getent passwd "$OWNER" | cut -d: -f6)"
AS=()
if [ "$(id -u)" = 0 ] && [ "$OWNER" != root ]; then AS=(runuser -u "$OWNER" --); fi
"${{AS[@]}}" env HOME="$HOME_DIR" GIT_TERMINAL_PROMPT=0 \\
  GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=20" git -C "$DIR" pull --ff-only > "$STATUS.pull" 2>&1
rc=$?
cat "$STATUS.pull"
if [ $rc -ne 0 ]; then
  say "failed pull $(tr -s '\\n\\t' '  ' < "$STATUS.pull" | cut -c1-400)"
  exit 1
fi
say install
echo "==> Putting it in"
if ! SUDO_USER="$OWNER" DEBIAN_FRONTEND=noninteractive bash "$DIR/setup.sh" --update < /dev/null; then
  say "failed install"
  exit 1
fi
say restart
echo "==> Restarting the Pi"
sleep 2
systemctl reboot
"""


def update_folder():
    """The pitato folder this was put in from (setup.sh tells the service where its settings are: the static
    folder in it), when it's a git clone; else None."""
    folder = os.path.dirname(os.path.abspath(STATIC))
    if os.path.isdir(os.path.join(folder, ".git")) and os.path.isfile(os.path.join(folder, "setup.sh")):
        return folder
    return None


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def update_why(status):
    """An update's 'failed ...', in words: what went wrong, and what to do."""
    words = status[len("failed"):].strip()
    if words.startswith("pull"):
        said = words[len("pull"):].lower()
        if any(w in said for w in ("fast-forward", "diverg", "rejected")):
            return "The update didn't start: this Pi's pitato folder has changes of its own (git pull says more)"
        if any(w in said for w in ("would be overwritten", "commit your changes", "unmerged", "conflict")):
            return "The update didn't start: files in the pitato folder were changed here (git pull says which)"
        if any(w in said for w in ("resolve host", "unable to access", "could not read from remote", "timed out",
                                   "unreachable", "connection")):
            return "The update didn't start: GitHub didn't answer. Is the WiFi on?"
        return "The update didn't start: git pull didn't work"
    if words.startswith("stopped"):
        return "The update stopped before it was done. Update software tries again"
    return "The update didn't finish putting it in. Update software tries again"


class Updater:
    """Whether there's a newer Pitato (looked at on a thread of its own, now and then), and the update itself."""

    def __init__(self, folder=None):
        self.folder = update_folder() if folder is None else folder or None
        self.lock = threading.Lock()
        self.new = 0               # newer versions (commits) waiting where it came from
        self.behind = False        # one pulled, but not put in yet (an update that didn't finish)
        self.looked = 0.0          # when it last looked (monotonic)
        self.looking = False
        self.started = 0.0         # an update under way since then (monotonic)
        self.unit_seen = (0.0, False)  # (when systemd was last asked, whether the update was still going then)
        self.wake = threading.Event()
        self.thread = None
        self.on_change = lambda: None   # (its thread: what it found)

    # -- what's there ---------------------------------------------------------------------------------------------
    def available(self):
        return bool(self.folder) and (self.new > 0 or self.behind)

    def words(self):
        """What System's Update software row says on its right."""
        return "New version" if self.new > 0 else "Finish updating" if self.behind else ""

    def owner(self):
        return pwd.getpwuid(os.stat(self.folder).st_uid)

    def git(self, *args, timeout=60):
        """git in the pitato folder, as its owner: (ok, what it said, its error)."""
        try:
            u = self.owner()
            env = dict(os.environ, HOME=u.pw_dir, **GIT_QUIET)
            kw = {}
            if os.geteuid() == 0 and u.pw_uid != 0:
                kw = {"user": u.pw_uid, "group": u.pw_gid, "extra_groups": os.getgrouplist(u.pw_name, u.pw_gid)}
            r = subprocess.run(["git", "-C", self.folder] + list(args), capture_output=True, text=True,
                               timeout=timeout, env=env, stdin=subprocess.DEVNULL, **kw)
        except (OSError, KeyError, ValueError, subprocess.TimeoutExpired) as ex:
            return False, "", str(ex)
        return r.returncode == 0, r.stdout.strip(), (r.stderr or "").strip()

    def check(self):
        """Looks: git fetch, then how many newer versions there are, and whether the one here is put in."""
        if not self.folder or self.started:
            return
        self.looking = True
        try:
            fetched, _, err = self.git("fetch", "--quiet", timeout=120)
            if not fetched:
                print(f"update: couldn't look for a newer version ({err.splitlines()[-1][:120] if err else 'git'})",
                      flush=True)
            ok, out, _ = self.git("rev-list", "--count", "HEAD..@{upstream}", timeout=30)   # (what it fetched last)
            here_ok, head, _ = self.git("rev-parse", "HEAD", timeout=30)
            put_in = read_text(INSTALLED)
            with self.lock:
                if ok and out.isdigit():
                    self.new = int(out)
                self.behind = bool(here_ok and put_in and put_in != head)
                self.looked = time.monotonic()
        finally:
            self.looking = False
        try:
            self.on_change()
        except Exception as ex:
            print(f"update: {ex!r}", flush=True)

    # -- its thread ------------------------------------------------------------------------------------------------
    def start(self):
        if self.folder and self.thread is None:
            self.thread = threading.Thread(target=self.run, daemon=True, name="update")
            self.thread.start()

    def run(self):
        due = time.monotonic() + UPDATE_FIRST
        while True:
            self.wake.wait(max(0.0, due - time.monotonic()))
            self.wake.clear()
            try:
                self.check()
            except Exception as ex:                        # (never stops for good)
                print(f"update: {ex!r}", flush=True)
            due = time.monotonic() + UPDATE_EVERY

    def poke(self):
        """System's open: it looks again now, unless it looked a little while ago."""
        if self.folder and not self.looking and time.monotonic() - self.looked > UPDATE_STALE:
            self.looked = time.monotonic()               # (asked once, however often System's opened meanwhile)
            self.wake.set()
            self.start()

    # -- the update --------------------------------------------------------------------------------------------------
    def begin(self):
        """Update software, pressed: the update's started (None), or why it can't be."""
        if not self.folder:
            return "This Pi wasn't set up from a git clone: it can't update by itself"
        if not shutil.which("systemd-run"):
            return "Can't update by itself here: run git pull, then sudo bash setup.sh"
        self.unit_seen = (0.0, False)
        if self.going():                               # (asked before its files are touched: they're that one's)
            return "It's updating already"
        try:
            os.makedirs(UPDATE_RUN, exist_ok=True)
            with open(UPDATE_SCRIPT, "w") as f:
                f.write(UPDATE_SH.format(status=shlex.quote(UPDATE_STATUS), log=shlex.quote(UPDATE_LOG)))
            os.chmod(UPDATE_SCRIPT, 0o700)
            with open(UPDATE_STATUS, "w") as f:
                f.write("start\n")
            owner = self.owner().pw_name
        except (OSError, KeyError) as ex:
            return f"The update didn't start ({ex})"
        cmd = ["systemd-run", "--quiet", "--collect", f"--unit={UPDATE_UNIT}", "--description=Pitato update",
               "/bin/bash", UPDATE_SCRIPT, self.folder, owner]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as ex:
            return f"The update didn't start ({ex})"
        if r.returncode != 0:
            said = (r.stderr or r.stdout or "").strip().splitlines()
            if said and "already" in said[-1]:
                return "It's updating already"
            return "The update didn't start" + (f" ({said[-1][:60]})" if said else "")
        print(f"update: started ({self.folder}, as {owner})", flush=True)
        self.started = time.monotonic()
        self.unit_seen = (self.started, True)
        return None

    def going(self):
        """The update's job is still running (systemd asked every few seconds at most)."""
        at, was = self.unit_seen
        if time.monotonic() - at < 3:
            return was
        try:
            r = subprocess.run(["systemctl", "is-active", "--quiet", UPDATE_UNIT], timeout=10)
            now = r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            now = was
        self.unit_seen = (time.monotonic(), now)
        return now

    def under_way(self):
        """An update that was going before media mode started (it was restarted meanwhile): taken up again."""
        status = read_text(UPDATE_STATUS)
        if status and not status.startswith("failed") and self.going():
            self.started = time.monotonic() - UPDATE_GRACE
            return True
        return False

    def progress(self):
        """How the update's getting on: ("going", words), ("restarting", words) or ("failed", why)."""
        status = read_text(UPDATE_STATUS)
        if status.startswith("failed"):
            return "failed", update_why(status)
        if status == "restart":
            return "restarting", "The new version starts in a moment"
        if time.monotonic() - self.started > UPDATE_GRACE and not self.going():
            return "failed", update_why("failed stopped")
        if status == "install":                        # (setup.sh's steps: what's after a colon is detail)
            steps = [line[4:].split(": ", 1)[0].strip() for line in read_text(UPDATE_LOG).splitlines()
                     if line.startswith("==> ")]
            return "going", steps[-1] if steps else "Putting it in"
        return "going", "Getting the new version"

    def done(self):
        """The update's over (it didn't work): System looks again, to show what's left to do."""
        self.started = 0.0
        self.looked = 0.0
        self.poke()
