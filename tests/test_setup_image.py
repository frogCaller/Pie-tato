"""setup.sh --image (for image/build.sh): the real setup.sh, start to end, in a mount namespace (setupspin/full/inner.sh)
on a 64-bit ARM Raspberry Pi OS that's not a Pi 4 or 5 (and not running: no terminal, nothing to answer with): no
questions at all; every emulator built, the N64's, PSP's and DS's too, and the PlayStation's for the Pi 3 and Zero 2
W's processor, which every 64-bit Pi runs; only the game folders every Pi plays; nothing restarted; what's put in
noted for Update software. With --gpi, the GPi Case's settings; with neither, HDMI's. And setup.sh by hand is as it
was (test_setup_full.py)."""
import os, re, shutil, subprocess, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
F = SP + "/setupspin/full"
ROOT = os.environ.get("PITATO_ROOT", ROOT)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


shutil.rmtree(F + "/repo", ignore_errors=True)
shutil.copytree(ROOT, F + "/repo", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
ASKS = ("Is this Pi in a RetroFlag", "Set the TV picture", "A camera's address", "Home Assistant address",
        "Reboot now?", "[Y/n]")


def run(args):
    for f in ("hold.log", "stub.log"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    env = dict(os.environ, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", SETUP_ARGS=args,
               SETUP_STDIN="/dev/null", SETUP_GIT="1", EXTRA_BIN=SP + "/setupspin/imagebin")
    env.pop("GIT_TERMINAL_PROMPT", None)
    p = subprocess.run(["unshare", "-m", "bash", F + "/inner.sh"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=1800)
    out = p.stdout + p.stderr
    stub = open(F + "/stub.log").read().splitlines() if os.path.exists(F + "/stub.log") else []
    return out, stub


def report(out, key):
    m = re.search(rf"^{key}: (.*)$", out, re.M)
    return m.group(1) if m else None


for args, kind in (("--image --no-gpi", "hdmi"), ("--image --gpi", "gpi"), ("--image", "hdmi")):
    out, stub = run(args)
    open(f"{F}/image_{kind}.out", "w").write(out)
    print(f"--- setup.sh {args}")
    asked = [a for a in ASKS if a in out]
    check(f"no questions ({asked}), right to the end (exit {report(out, 'SETUP EXIT')})",
          not asked and report(out, "SETUP EXIT") == "0" and "All set, for the image" in out
          and "setup.sh stopped before it was done" not in out)
    check("...nothing restarted, and no reboot (it starts on the Pi it's written for)",
          not any(s.startswith("reboot") for s in stub) and "systemctl restart pitato" not in stub
          and "Reboot to" not in out)
    if args == "--image --no-gpi" or args == "--image":
        check("...a screen on HDMI (no GPi Case settings)", "Setting up for a screen on HDMI" in out
              and report(out, "GPI OVERLAY") == "[]" and "gpi-case setup" not in report(out, "CONFIG"))
    else:
        check(f"...the GPi Case's settings ({report(out, 'GPI OVERLAY')})",
              "Setting up for the GPi Case 2W: its screen, speaker and buttons." in out
              and "gpicase-dpi.dtbo" in report(out, "GPI OVERLAY") and "gpi-case setup" in report(out, "CONFIG"))
    if args != "--image --no-gpi":
        continue
    check(f"...the PlayStation's emulator built for the Pi 3 and Zero 2 W's processor ({report(out, 'PCSX')})",
          report(out, "PCSX") == "[platform=rpi3_64 ]")
    steps = [s for s in ("Building the N64 emulator", "Building the PSP emulator", "Building the DS emulator")
             if s in out]
    check(f"...the N64's, PSP's and DS's emulators too, though this computer's no Pi 4 or 5 ({steps})",
          len(steps) == 3 and "need a Pi 4 or 5" not in out)
    check(f"...only the game folders every Pi plays ({report(out, 'GAMES')})",
          report(out, "GAMES") == "[BIOS gb gba gbc genesis gg neogeo nes ngp ngpc ps1 sms snes ]")
    check(f"...what's put in, noted for Update software ({report(out, 'INSTALLED')})",
          report(out, "INSTALLED") == report(out, "HEAD") and len(report(out, "HEAD")) == 42)
    check(f"...the services it'd start at start-up, as by hand ({report(out, 'UNITS')})",
          report(out, "UNITS") == "[bluealsa.service.d getty@tty1.service.d pitato-web.service pitato.service ]")
    check("...Home Assistant left for later", "No Home Assistant yet: add it any time in its Settings, on the Pi or the web page." in out)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
