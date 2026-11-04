"""stop.sh, start.sh and uninstall.sh, each run for real after the real setup.sh (setupspin/full/inner.sh, in a
mount namespace). A PC with Ubuntu's desktop: stop.sh turns Pietato off (its services stopped, and not started with
the computer), the computer starting in its desktop again, the desktop started now if it isn't running; start.sh
turns it back on (in place of the desktop: after a restart while the desktop's up, at once while it isn't);
uninstall.sh takes it off (services, programs, the emulators setup.sh built but not one of yours, what it kept, the
web page's sound card and its pictures' copies, signing you in by itself), leaving your files and the Pietato
folder, the desktop at start-up again. A Pi in a GPi Case 2W: stop.sh says to shut down before switching off;
uninstall.sh puts RetroFlag's safe-shutdown script back in rc.local and leaves the case's screen settings. Asked
first: anything but y changes nothing. Without sudo: says so."""
import os, re, shutil, subprocess
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
F = SP + "/setupspin/full"
ROOT = os.environ.get("PITATO_ROOT", ROOT)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


assert not os.path.exists("/etc/rc.local"), "this machine has an rc.local of its own: the test would replace it"
shutil.rmtree(F + "/repo", ignore_errors=True)
shutil.copytree(ROOT, F + "/repo", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))


def run(after, pc, **extra):
    for f in ("hold.log", "stub.log"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    env = dict(os.environ, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", AFTER=after, SETUP_GIT="1", **extra)
    if pc:
        env.update(PC_MODE="1", DESKTOP_DM="1", STUB_DEFAULT_TARGET="graphical.target",
                   EXTRA_BIN=SP + "/setupspin/pcbin_desk", SETUP_STDIN=SP + "/setupspin/pc_answers.txt",
                   SETUP_ARGS="--no-gpi")
    env.pop("GIT_TERMINAL_PROMPT", None)
    env.pop("PITATO_MODEL_FILE", None)
    p = subprocess.run(["unshare", "-m", "bash", F + "/inner.sh"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=1800)
    out = p.stdout + p.stderr
    stub = open(F + "/stub.log").read() if os.path.exists(F + "/stub.log") else ""
    return out, stub


def step(out, stub, cmd):
    """What a step said, what it asked systemctl, and what was left after it."""
    said = out.split(f"=== {cmd}\n", 1)[1].split(f"=== EXIT {cmd}:", 1)
    rc = int(said[1].split("\n", 1)[0])
    rest = said[1].split("\n", 1)[1]
    left = dict(re.findall(r"^([A-Z]+) AFTER: (.*)$", rest.split("=== ", 1)[0], re.M))
    asked = stub.split(f"### {cmd}\n", 1)[1].split("### ", 1)[0].splitlines()
    return said[0].strip().splitlines(), rc, asked, left


# ---- a PC with Ubuntu's desktop ----
out, stub = run("stop.sh|start.sh@display-manager|start.sh|uninstall.sh|uninstall.sh --yes", pc=True)
open(SP + "/out/stop_uninstall_pc.out", "w").write(out)
check(f"setup.sh first, as on a PC ({re.search(r'SETUP EXIT: (.*)', out).group(1)})",
      "SETUP EXIT: 0" in out and "systemctl set-default multi-user.target" in stub)
said, rc, asked, left = step(out, stub, "stop.sh")
check(f"stop.sh: Pietato's services stopped, and not started with the computer ({[a for a in asked if 'disable' in a]})",
      rc == 0 and "systemctl --quiet disable --now pitato" in asked and "systemctl --quiet disable --now pitato-web" in asked
      and not any("pitato-camera" in a for a in asked))
check(f"...the computer starts in its desktop again, started now as it wasn't running ({said})",
      "systemctl set-default graphical.target" in asked and "systemctl --no-block start display-manager" in asked
      and said == ["Pietato's off: it won't start with the computer. sudo bash start.sh turns it back on.",
                   "The computer starts in its desktop again."])
check(f"...and everything kept ({left['UNITS']}, {left['VARLIB']})",
      "pitato.service" in left["UNITS"] and "pitato-web.service" in left["UNITS"] and "pitato" in left["LOCAL"]
      and "was-graphical" in left["VARLIB"] and "pcsx_rearmed_libretro.so" in left["CORES"])
said, rc, asked, left = step(out, stub, "start.sh")
check(f"start.sh with the desktop up: on again, in place of the desktop, after a restart ({said})",
      rc == 0 and "systemctl --quiet enable --now pitato-web" in asked and "systemctl --quiet enable pitato" in asked
      and "systemctl set-default multi-user.target" in asked and "systemctl start pitato" not in asked
      and said == ["Pietato's on: restart the computer and it starts in Pietato instead of the desktop."])
said2 = out.split("=== start.sh\n")[2].split("=== EXIT start.sh:")[0].strip().splitlines()
asked2 = stub.split("### start.sh\n")[2].split("### ")[0].splitlines()
check(f"...without the desktop up: on at once ({said2})", "systemctl start pitato" in asked2
      and said2 == ["Pietato's on, now and every time the computer starts."])
said, rc, asked, left = step(out, stub, "uninstall.sh")
check(f"uninstall.sh: asked first, and no answer changes nothing ({said[-1:]}, {left['UNITS']})",
      rc == 0 and said[-1] == "Nothing changed." and "pitato.service" in left["UNITS"] and not asked)
said, rc, asked, left = step(out, stub, "uninstall.sh --yes")
check(f"uninstall.sh --yes: its services stopped and gone ({left['UNITS']})", rc == 0
      and "systemctl --quiet disable --now pitato" in asked and "systemctl daemon-reload" in asked
      and not re.search(r"\bpitato", left["UNITS"]) and "getty@tty1.service.d" not in left["UNITS"])
check(f"...its programs, what it kept, and the emulators it built, not one of yours ({left['LOCAL']}, {left['CORES']})",
      "pitato" not in left["LOCAL"].split("[", 1)[1] and left["VARLIB"] == "[]" and left["CORES"] == "[other_libretro.so ]")
check(f"...the web page's sound card and Chromium's session gone, and its copies of your pictures ({left['ETC']}, {left['HOME']})",
      left["ETC"] == "[] []" and left["HOME"].endswith("[]"))
check(f"...your files and the Pietato folder still here ({left['HOME']})",
      "pitato" in left["HOME"].split("]")[0] and "Videos" in left["HOME"] and "mine.mp4" in left["HOME"])
check(f"...the desktop at start-up again, and now ({said[-3:]})",
      "systemctl set-default graphical.target" in asked and asked[-1] == "systemctl --no-block start display-manager"
      and said[-1] == "The computer starts in its desktop again.")
check("...says what stays, and that the console asks for your password again",
      "Pietato is removed from this computer." in said and "The console asks for your password at start-up again." in said
      and any("delete it too if you don't need them" in s for s in said))

# ---- a Pi in a GPi Case 2W, with RetroFlag's safe-shutdown script in rc.local ----
out, stub = run("stop.sh|uninstall.sh --yes", pc=False, GPI_BLOCK="1", SETUP_ARGS="--update", SETUP_STDIN="/dev/null",
                RCLOCAL_INIT=SP + "/setupspin/rclocal_retroflag.txt")
open(SP + "/out/stop_uninstall_pi.out", "w").write(out)
os.remove("/etc/rc.local")                     # (this machine has none of its own)
check(f"setup.sh first, a Pi in the GPi Case 2W: RetroFlag's script turned off ({re.search(r'SETUP EXIT: (.*)', out).group(1)})",
      "SETUP EXIT: 0" in out and "Turned off RetroFlag's SafeShutdown.py in /etc/rc.local" in out)
said, rc, asked, left = step(out, stub, "stop.sh")
check(f"stop.sh on a Pi: off, the start-up as it is, and shut down before switching the case off ({said})",
      rc == 0 and not any("set-default" in a or "display-manager" in a for a in asked)
      and said[-1].startswith("In the GPi Case, run  sudo poweroff  before you switch it off"))
said, rc, asked, left = step(out, stub, "uninstall.sh --yes")
check(f"uninstall.sh: RetroFlag's script back on ({left['RCLOCAL']})", rc == 0
      and left["RCLOCAL"] == "[#!/bin/sh -e|# rc.local|sudo python3 /opt/RetroFlag/SafeShutdown.py &|exit 0|]"
      and "RetroFlag's safe-shutdown script is back on in /etc/rc.local." in said)
check(f"...the case's screen settings kept ({left['CONFIG']}), and the start-up target left be",
      left["CONFIG"] == "[2]" and not any("set-default" in a for a in asked)
      and "The GPi Case's screen and sound settings stay in config.txt, so the case keeps working." in said)

# ---- without sudo ----
nb = "/var/tmp/pietato-nosudo-test2"     # (somewhere gpitest can read them: perhaps not the Pietato folder)
shutil.rmtree(nb, ignore_errors=True)
os.makedirs(nb)
os.chmod(nb, 0o755)
for name in ("stop.sh", "start.sh", "uninstall.sh"):
    shutil.copy(f"{ROOT}/{name}", f"{nb}/{name}")
    os.chmod(f"{nb}/{name}", 0o644)
    r = subprocess.run(["runuser", "-u", "gpitest", "--", "bash", f"{nb}/{name}"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, cwd=nb)
    check(f"{name} without sudo: says so ({r.stdout.strip()!r})", r.returncode == 1
          and r.stdout.strip() == f"Run with sudo:  sudo bash {name}")
shutil.rmtree(nb, ignore_errors=True)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
