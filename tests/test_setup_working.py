"""setup.sh's moving line while it downloads and builds the emulators (working, spin), and what it does until it's
done (a shutdown asked for gently held off; if it stops early, it says so and tidies up): setup.sh's own code, cut
out of it and run here on a pretend screen (a pty, Ctrl+C typed on it, a narrow one too) and into a file."""
import fcntl, os, pty, re, select, signal, struct, subprocess, termios, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/setupspin"
VT = S + "/vartmp"
SETUP = os.environ.get("PITATO_ROOT", ROOT) + "/setup.sh"
os.makedirs(VT, exist_ok=True)
for f in os.listdir(S):
    if f.endswith((".sh", ".holds", ".log", ".out")):
        os.remove(os.path.join(S, f))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


src = open(SETUP).read()
a = src.index("step() {")
b = src.index("\n}\n", src.index("fetch_source() {")) + 3
c = src.index("# Until it's done")
d = src.index("\n", src.index("trap 'exit 130' INT", c)) + 1          # (to its Ctrl+C trap)
HEAD = ("#!/usr/bin/env bash\nset -e\n"
        'MACHINE="${MACHINE:-Pi}"     # (setup.sh sets it before this: the Pi, or on a PC the computer)\n'
        + src[a:b] + "\n" + src[c:d] + "\n")
WATCHER = "while kill -0"                         # (the hold's own command, as setup.sh gives it)


def harness(name, body):
    p = f"{S}/{name}.sh"
    open(p, "w").write(HEAD + body)
    return p


def env_for(name, extra=None):
    e = dict(os.environ, PATH=S + "/bin:" + os.environ["PATH"], HOLD_LOG=f"{S}/{name}.holds", VT=VT, **(extra or {}))
    e.pop("COLUMNS", None)
    e.pop("GIT_TERMINAL_PROMPT", None)               # (as on a Pi: git may ask)
    return e


def on_pty(name, body, cols=80, keys=(), sig=None, timeout=60, env=None):
    """bash runs BODY (after setup.sh's code) on a pretend screen COLS wide. KEYS: (after, bytes) typed on it;
    SIG: (after, signal) sent to it. Its output, how it ended, and its pid."""
    script = harness(name, body)
    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, cols, 0, 0))
        os.execvpe("bash", ["bash", script], env_for(name, env))
    t0, out, keys, status = time.monotonic(), b"", list(keys), None
    while time.monotonic() - t0 < timeout:
        now = time.monotonic() - t0
        while keys and keys[0][0] <= now:
            os.write(fd, keys.pop(0)[1])
        if sig and sig[0] <= now:
            os.kill(pid, sig[1]); sig = None
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""
            if not chunk:
                break
            out += chunk
        if status is None:
            done, st = os.waitpid(pid, os.WNOHANG)
            if done:
                status = st
    if status is None:
        status = os.waitpid(pid, 0)[1]
    os.close(fd)
    return out.decode("utf-8", "replace"), status, pid


def frames(out):
    """What the screen showed, line by line: each redraw of the moving line on its own."""
    return [f.replace("\x1b[K", "") for f in re.split(r"[\r\n]+", out) if f.replace("\x1b[K", "").strip()]


def spinning(fs, what):
    return [f for f in fs if re.match(r"^  [|/\\-] " + what + r"( \d+%)?  \d+:\d\d  Still working: leave the Pi on$", f)]


def alive_with(text):
    found = []
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                cmd = open(f"/proc/{p}/cmdline", "rb").read().replace(b"\0", b" ").decode("utf-8", "replace")
            except OSError:
                continue
            if text in cmd:
                found.append((int(p), cmd))
    return found


def watcher_of(pid):
    """the hold's own command (it ends when setup.sh does), for setup.sh as PID"""
    return [w for w in alive_with(f"done _ {pid} ") if WATCHER in w[1]]


def settle(cond, secs=5):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.1)
    return bool(cond())


def holds(name):
    try:
        return open(f"{S}/{name}.holds").read().splitlines()
    except OSError:
        return []


# ---- without a screen: a line a minute (started first: it takes a minute) ----
notty = subprocess.Popen(["bash", harness("notty", 'log=$(mktemp "$VT/n-XXXXXX")\n'
                                                   'working "Building" "$log" sleep 62 && echo "RC=0"\n'
                                                   'rm -f "$log"; FINISHED=yes\n')],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env_for("notty"), text=True)

# ---- elapsed ----
got = subprocess.run(["bash", "-c", HEAD.split("# Until it's done")[0] + "\nfor t in 0 9 65 599 3600 3725 36000; do "
                      "elapsed $t; echo; done"], capture_output=True, text=True).stdout.split()
check(f"how long it's taken: {got}", got == ["0:00", "0:09", "1:05", "9:59", "1:00:00", "1:02:05", "10:00:00"])

# ---- a download, then a build that says how far it's got ----
OK = r'''
fake_build() { for p in 5 20 37 60 85 100; do echo "[ $p%] Building CXX object part$p.o"; sleep 0.6; done; }
tmp=$(mktemp -d "$VT/ok-XXXXXX"); BUILDING="$tmp"
echo "the hold: $(kill -0 "$HOLD" 2> /dev/null && echo on || echo off)"
working "Downloading" "$tmp/build.log" sleep 2.2 \
  && working "Building" "$tmp/build.log" fake_build \
  || echo "FAILED"
echo "its log: $(grep -c '%\]' "$tmp/build.log") lines"
rm -rf "$tmp"
FINISHED=yes
h=$HOLD; let_go
echo "the hold: $(kill -0 "$h" 2> /dev/null && echo on || echo off)"
echo "All set."
'''
out, st, pid = on_pty("ok", OK)
fs = frames(out)
dl, bl = spinning(fs, "Downloading"), spinning(fs, "Building")
check(f"downloading: a line that moves ({len(dl)} redraws, {sorted(set(f[2] for f in dl))})",
      len(dl) >= 2 and len(set(f[2] for f in dl)) >= 2)
check(f"...then done, on a line of its own ({[f for f in fs if 'Downloading:' in f]})",
      any(re.fullmatch(r"  Downloading: done \(took 0:0[23]\)", f) for f in fs))
pcts = [int(m.group(1)) for f in bl for m in [re.search(r"Building (\d+)%", f)] if m]
check(f"building: how far it's got, as the build says ({pcts})", pcts and pcts == sorted(pcts)
      and set(pcts) <= {5, 20, 37, 60, 85, 100} and len(set(pcts)) >= 2)
times = [re.search(r"  (\d+:\d\d)  Still", f).group(1) for f in bl]
check(f"...the time it's taken, counting up ({times})", times and times == sorted(times, key=lambda s: int(s.replace(':', ''))))
check(f"...then done ({[f for f in fs if 'Building:' in f]})", any(re.fullmatch(r"  Building: done \(took 0:0[34]\)", f)
                                                                  for f in fs))
check("...the moving line wiped first: nothing of it left before 'done'",
      re.search(r"\r\x1b\[K  Building: done", out) is not None and re.search(r"\r\x1b\[K  Downloading: done", out) is not None)
check("its output in its log, not on the screen", "its log: 6 lines" in fs and not any("CXX object" in f for f in fs))
check(f"held while it worked, let go once done ({[f for f in fs if f.startswith('the hold')]})",
      fs.count("the hold: on") == 1 and "the hold: off" in fs and fs.index("the hold: off") < fs.index("All set."))
h = holds("ok")
held_by = h[0].split()[1] if h and h[0].startswith("held ") else "?"
check(f"...the hold asked for: shutting down, sleep and the power button, until it's let go ({h})",
      len(h) == 2 and "--what=shutdown:sleep:handle-power-key | --mode=block | --who=Pietato setup | "
      "--why=Setting up Pietato: leave the Pi on until it says All set" in h[0] and h[1] == f"let go {held_by}")
check(f"finished: no word of stopping early, and it ended well ({os.waitstatus_to_exitcode(st)})",
      "stopped before" not in out and os.waitstatus_to_exitcode(st) == 0)
check("nothing left running (the hold's own command, the moving line)",
      settle(lambda: not watcher_of(pid) and not alive_with(S + "/ok.sh")))

# ---- on a PC: the computer to leave on, not the Pi ----
PC_BODY = r'''
tmp=$(mktemp -d "$VT/pc-XXXXXX"); BUILDING="$tmp"
working "Building" "$tmp/build.log" sleep 1.6 || echo "FAILED"
rm -rf "$tmp"
FINISHED=yes
let_go
'''
out, st, pid = on_pty("pc", PC_BODY, env={"MACHINE": "computer"})
fs = frames(out)
pcl = [f for f in fs if re.match(r"^  [|/\\-] Building  \d+:\d\d  Still working: leave the computer on$", f)]
h = holds("pc")
check(f"on a PC: leave the computer on, on the moving line and in the hold ({len(pcl)} redraws, {h[:1]})",
      pcl and not any("leave the Pi on" in f for f in fs)
      and h and "--why=Setting up Pietato: leave the computer on until it says All set" in h[0])

# ---- a narrow screen: one line, however narrow ----
out, st, pid = on_pty("narrow", OK.replace("sleep 0.6", "sleep 0.4"), cols=40)
fs = frames(out)
moving = [f for f in fs if re.match(r"^  [|/\\-] ", f)]
check(f"40 wide: the moving line cut to fit ({max(len(f) for f in moving) if moving else None} wide, "
      f"{moving[:1]})", moving and max(len(f) for f in moving) <= 39 and all(len(f) == 39 for f in moving))

# ---- a build that goes wrong ----
out, st, pid = on_pty("fail", r'''
tmp=$(mktemp -d "$VT/fail-XXXXXX"); BUILDING="$tmp"
working "Building" "$tmp/build.log" bash -c 'echo "[ 50%] half"; sleep 1.5; echo "error: no"; exit 3' \
  && echo "RC=0" || echo "RC=$?"
tail -n 1 "$tmp/build.log"; rm -rf "$tmp"
FINISHED=yes
''')
fs = frames(out)
check(f"a build that goes wrong: its exit status, no 'done' ({fs[-3:]})",
      "RC=3" in fs and not any("done" in f for f in fs) and "error: no" in fs)
check("...the moving line wiped first", re.search(r"\r\x1b\[KRC=3", out) is not None)

# ---- quick jobs, over and over: no stray messages from the moving line ----
out, st, pid = on_pty("quick", r'''
log=$(mktemp "$VT/q-XXXXXX")
for n in $(seq 40); do working "Quick" "$log" true; working "Quick" "$log" false || true; done
rm -f "$log"; FINISHED=yes; echo "end"
''')
fs = frames(out)
DONE = r"  Quick: done \(took 0:0[01]\)"           # (whole seconds: a quick one can cross into the next)
stray = [f for f in fs if not re.fullmatch(DONE + "|end", f) and f not in spinning(fs, "Quick")]
check(f"quick jobs, 80 of them: nothing but 'done' ({len([f for f in fs if 'done' in f])}, stray: {stray[:3]})",
      len([f for f in fs if re.fullmatch(DONE, f)]) == 40 and not stray and os.waitstatus_to_exitcode(st) == 0)

# ---- nothing waits for the keyboard unseen ----
out, st, pid = on_pty("keys", r'''
log=$(mktemp "$VT/k-XXXXXX")
f() { local -x GIT_TERMINAL_PROMPT=0; env | grep '^GIT_TERMINAL_PROMPT='; read -r x; echo "read: $?"; }
working "Downloading" "$log" f && cat "$log"; rm -f "$log"
echo "after: ${GIT_TERMINAL_PROMPT-unset}"; FINISHED=yes
''', timeout=10)
fs = frames(out)
check(f"a job that asks: no keyboard, so no waiting ({fs})", "read: 1" in fs and "GIT_TERMINAL_PROMPT=0" in fs
      and "after: unset" in fs)

# ---- Ctrl+C while it builds ----
LONG = r'''
tmp=$(mktemp -d "$VT/long-XXXXXX"); BUILDING="$tmp"; echo "folder: $tmp"
long_build() { for p in $(seq 20); do echo "[ $((p * 5))%] Building part$p.o"; sleep 1; done; }
working "Building" "$tmp/build.log" long_build && echo "BUILT"
echo "not reached"
'''
out, st, pid = on_pty("ctrlc", LONG, keys=[(2.6, b"\x03")])
fs = frames(out)
folder = next((f.split(": ", 1)[1] for f in fs if f.startswith("folder: ")), "")
check(f"Ctrl+C while it builds: it stops, and says so ({fs[-2:]})",
      "setup.sh stopped before it was done. Run  sudo bash setup.sh  again to finish." in fs
      and "not reached" not in fs and "BUILT" not in fs)
check(f"...how it ended: by Ctrl+C ({st}, {os.waitstatus_to_exitcode(st)})", os.waitstatus_to_exitcode(st) in (130, -2))
check("...the moving line wiped first", re.search(r"\r\x1b\[K\s*\nsetup\.sh stopped", out.replace("^C", "")) is not None)
check(f"...the emulator's folder taken away ({folder})", folder.startswith(VT) and not os.path.exists(folder))
check("...the hold let go, and nothing left running",
      settle(lambda: not watcher_of(pid) and not alive_with(S + "/ctrlc.sh")))

# ---- stopped some other way (kill) ----
out, st, pid = on_pty("term", LONG, sig=(2.2, signal.SIGTERM))
fs = frames(out)
folder = next((f.split(": ", 1)[1] for f in fs if f.startswith("folder: ")), "")
check(f"stopped with kill: says so, and tidies up ({fs[-1:]}, {folder})",
      "setup.sh stopped before it was done. Run  sudo bash setup.sh  again to finish." in fs
      and "not reached" not in fs and folder.startswith(VT) and not os.path.exists(folder))
check("...the hold let go, nothing left running",
      settle(lambda: not watcher_of(pid) and not alive_with(S + "/term.sh")))

# ---- killed outright (kill -9): the hold and the moving line end by themselves ----
# (setup.sh run from a shell, as it is: not the terminal's first process, which takes everything with it as it goes)
script = harness("kill9", LONG)
outer, fd = pty.fork()
if outer == 0:
    os.execvpe("bash", ["bash", "-c", f'bash {script} & echo "inner $!"; wait; sleep 5'], env_for("kill9"))
out, inner, killed_at, t0 = "", None, None, time.monotonic()
while time.monotonic() - t0 < 30:
    r, _, _ = select.select([fd], [], [], 0.1)
    if r:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            chunk = b""
        if not chunk:
            break
        out += chunk.decode("utf-8", "replace")
    m = re.search(r"inner (\d+)", out)
    if m and inner is None:
        inner, started = int(m.group(1)), time.monotonic()
    if inner and killed_at is None and time.monotonic() - started > 2.2:
        os.kill(inner, signal.SIGKILL); killed_at = time.monotonic()
os.waitpid(outer, 0); os.close(fd)
h = holds("kill9")
held_by = h[0].split()[1] if h and h[0].startswith("held ") else "0"
gone = settle(lambda: not watcher_of(inner) and not alive_with(script) and not os.path.exists(f"/proc/{held_by}"), 6)
check(f"killed outright: the moving line and the hold end by themselves ({holds('kill9')})",
      killed_at and gone and holds("kill9") == [h[0], f"ended {held_by}"])
for f in os.listdir(VT):
    if f.startswith("long-"):
        os.system(f"rm -rf '{VT}/{f}'")             # (kill -9: nothing tidies up, as expected)

# ---- without a screen ----
txt = notty.communicate(timeout=120)[0]
check(f"without a screen: a line a minute, no moving line ({txt.splitlines()})",
      txt.splitlines()[0::2] == ["  Building: still working (1 min so far)", "RC=0"]
      and re.fullmatch(r"  Building: done \(took 1:0[23]\)", txt.splitlines()[1])
      and "\r" not in txt and "\x1b" not in txt)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
