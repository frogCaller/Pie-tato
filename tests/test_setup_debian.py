"""setup.sh on a PC with Debian (12 or 13, Intel or AMD): the real setup.sh, start to end, in a mount namespace
(setupspin/full/inner.sh, PC_MODE), with Debian's os-release and an /etc/apt of its own (its sources as Debian's
installer writes them), apt-get and apt-cache stood in for (Snes9x and Genesis Plus GX there only with non-free on), and
no network for the emulators' sources. Debian 13 with a desktop: it says it's setting up this computer; Debian's
non-free packages turned on (the installer's sources.list: non-free beside main on Debian's lines), apt-get update run
again, then the SNES and Genesis emulators asked for; Chromium from Debian (chromium, never Ubuntu's chromium-browser);
kbd and openssl, avahi-daemon (NAME.local); no linux-modules-extra (Ubuntu's: Debian's kernel has the Loopback card);
the terminal at start-up, PipeWire left the Loopback card, BlueALSA out. Debian 12 without a desktop: the same for
bookworm, rfkill and BlueALSA in. An update with non-free on already: sources untouched, one apt-get update. Run with
su (Debian without sudo: no SUDO_USER, a PATH without sbin): you found by the Pietato folder (yours), signed in by
yourself at start-up, the web page as you, and nothing "command not found". And without sudo there at all,
setup.sh, stop.sh, start.sh and uninstall.sh say to use su -c."""
import os, re, shutil, subprocess, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
F = SP + "/setupspin/full"
D = SP + "/setupdebian"
ROOT = os.environ.get("PITATO_ROOT", ROOT)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


shutil.rmtree(F + "/repo", ignore_errors=True)
shutil.copytree(ROOT, F + "/repo", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
shutil.rmtree(D, ignore_errors=True)
os.makedirs(D)

INSTALLER = """#deb cdrom:[Debian GNU/Linux {n}.1.0 _{N}_ - Official amd64 DVD Binary-1 with firmware]/ {c} contrib main non-free-firmware

deb http://deb.debian.org/debian/ {c} main non-free-firmware
deb-src http://deb.debian.org/debian/ {c} main non-free-firmware

deb http://security.debian.org/debian-security {c}-security main non-free-firmware
deb-src http://security.debian.org/debian-security {c}-security main non-free-firmware

# {c}-updates, to get updates before a point release is made;
deb http://deb.debian.org/debian/ {c}-updates main non-free-firmware
deb-src http://deb.debian.org/debian/ {c}-updates main non-free-firmware
"""


def debian(n, code):
    path = f"{D}/os-release-{n}"
    open(path, "w").write(f'PRETTY_NAME="Debian GNU/Linux {n} ({code})"\nNAME="Debian GNU/Linux"\nVERSION_ID="{n}"\n'
                          f'VERSION="{n} ({code})"\nVERSION_CODENAME={code}\nID=debian\n'
                          'HOME_URL="https://www.debian.org/"\n')
    return path


def apt_dir(name, sources):
    d = f"{D}/apt-{name}"
    os.makedirs(d + "/sources.list.d")
    open(d + "/sources.list", "w").write(sources)
    return d


def run(osr, apt, desktop, update=False, su=False):
    for f in ("hold.log", "stub.log"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    bins = [SP + "/setupspin/debbin", SP + ("/setupspin/pcbin_desk" if desktop else "/setupspin/pcbin")]
    env = dict(os.environ, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", PC_MODE="1", OS_RELEASE=osr,
               APT_DIR=apt, SETUP_STDIN="/dev/null" if update else SP + "/setupspin/pc_answers.txt",
               SETUP_GIT="1", EXTRA_BIN=":".join(bins),
               STUB_DEFAULT_TARGET="graphical.target" if desktop else "multi-user.target",
               SETUP_ARGS="--update" if update else "--no-gpi")
    if desktop:
        env["DESKTOP_DM"] = "1"
    if su:
        env["AS_SU"] = "1"
    for k in ("GIT_TERMINAL_PROMPT", "PITATO_MODEL_FILE", "PITATO_OS_RELEASE"):
        env.pop(k, None)
    p = subprocess.run(["unshare", "-m", "bash", F + "/inner.sh"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=1800)
    out = p.stdout + p.stderr
    stub = open(F + "/stub.log").read().splitlines() if os.path.exists(F + "/stub.log") else []
    return out, stub


def report(out, key):
    m = re.search(rf"^{re.escape(key)}: (.*)$", out, re.M)
    return m.group(1) if m else None


def first_install(stub):
    return next((i for i, s in enumerate(stub) if s.startswith("apt-get install")), len(stub))


# ---- Debian 13 (trixie), with a desktop ----
apt13 = apt_dir("13", INSTALLER.format(n=13, N="Trixie", c="trixie"))
out, stub = run(debian(13, "trixie"), apt13, desktop=True)
open(SP + "/out/setup_debian13_desktop.out", "w").write(out)
lines = out.splitlines()
check(f"Debian 13 with a desktop: it says it's setting up this computer (exit {report(out, 'SETUP EXIT')}, "
      f"os {report(out, 'OS')})", "Setting up this computer. Plug in any USB or Bluetooth game controller." in lines
      and report(out, "SETUP EXIT") == "0" and report(out, "OS") == "[debian]")
check("Debian's non-free packages turned on, and said so",
      "Turning on Debian's non-free packages: the SNES and Genesis emulators are there." in lines
      and "Non-free is on now in: /etc/apt/sources.list" in lines)
src = open(apt13 + "/sources.list").read()
check("...non-free beside main on each of Debian's lines (deb and deb-src, security and updates too), the CD's "
      "line and the comments as they were", src == "".join(
          l if l.startswith("#") else l.replace(" main non-free-firmware", " main non-free non-free-firmware")
          for l in INSTALLER.format(n=13, N="Trixie", c="trixie").splitlines(True)))
first = first_install(stub)
check(f"...apt-get update again before anything's installed ({stub[:first]})",
      stub[:first].count("apt-get update") == 2 and "apt-cache policy libretro-snes9x" in stub[:first])
check("...then the SNES and Genesis emulators asked for",
      "apt-get install -y libretro-snes9x" in stub and "apt-get install -y libretro-genesisplusgx" in stub)
check("kbd (chvt) and openssl (the secure page) with the rest, and avahi-daemon (NAME.local on a server too)",
      any(s.startswith("apt-get install -y python3-evdev ") and s.endswith(" bluez kbd openssl") for s in stub)
      and "apt-get install -y avahi-daemon" in stub)
check("Chromium from Debian (chromium), never Ubuntu's chromium-browser, and libpam-systemd for its session",
      "apt-get install -y chromium" in stub and not any("chromium-browser" in s for s in stub)
      and any(s.startswith("apt-get install -y cage ") and s.endswith(" libpam-systemd") for s in stub))
check("no linux-modules-extra (Ubuntu's): it says the Loopback card loads after a restart (not loadable here)",
      not any("linux-modules-extra" in s for s in stub)
      and "(The Loopback sound card didn't load yet: Sound here and Mic here work after a restart.)" in lines)
check("the terminal at start-up instead of the desktop, as on Ubuntu",
      "systemctl set-default multi-user.target" in stub
      and "==> This computer starts in Pietato now, not the desktop (System > Desktop starts the desktop)" in lines)
check(f"PipeWire leaves the Loopback card alone, 0.4's way and 0.5's (Debian 13's) ({report(out, 'WIREPLUMBER')})",
      report(out, "WIREPLUMBER") == "[./main.lua.d/51-pietato-loopback.lua ./wireplumber.conf.d/51-pietato-loopback.conf ]")
check("BlueALSA left out (the desktop's PipeWire has Bluetooth's sound)", not any("bluez-alsa" in s for s in stub))
check(f"the PlayStation emulator built for a PC, every emulator tried ({report(out, 'PCSX')})",
      report(out, "PCSX") == "[platform=unix ]" and "(Couldn't build Dolphin: GameCube and Wii games won't start.)" in out)
check(f"you: who ran sudo, as before ({report(out, 'WEB USER')}, {report(out, 'AUTOLOGIN')})",
      report(out, "WEB USER") == "[gpitest]" and report(out, "AUTOLOGIN") == "[--autologin gpitest]")
check("All set, and nothing 'command not found'", "All set. Reboot to start." in lines and "command not found" not in out)

# ---- an update, with non-free on already ----
out, stub = run(debian(13, "trixie"), apt13, desktop=True, update=True)
first = first_install(stub)
check(f"an update with non-free on: sources untouched, apt-get update once ({stub[:first]}, exit "
      f"{report(out, 'SETUP EXIT')})", report(out, "SETUP EXIT") == "0" and stub[:first].count("apt-get update") == 1
      and open(apt13 + "/sources.list").read() == src and "non-free" not in out.lower().split("==> installing packages")[1][:600])

# ---- Debian 12 (bookworm), no desktop ----
apt12 = apt_dir("12", INSTALLER.format(n=12, N="Bookworm", c="bookworm"))
out, stub = run(debian(12, "bookworm"), apt12, desktop=False)
open(SP + "/out/setup_debian12_server.out", "w").write(out)
lines = out.splitlines()
check(f"Debian 12 without a desktop: set up (exit {report(out, 'SETUP EXIT')}), non-free on for bookworm",
      report(out, "SETUP EXIT") == "0" and "Non-free is on now in: /etc/apt/sources.list" in lines
      and open(apt12 + "/sources.list").read().count("bookworm main non-free non-free-firmware") == 2
      and open(apt12 + "/sources.list").read().count("main non-free non-free-firmware") == 6)
check("...the start-up target left be, rfkill and BlueALSA in, nothing for PipeWire",
      not any("set-default" in s for s in stub) and "apt-get install -y rfkill" in stub
      and "apt-get install -y bluez-alsa-utils libasound2-plugin-bluez" in stub and report(out, "WIREPLUMBER") == "[]")

# ---- with su (Debian without sudo) ----
apt13b = apt_dir("13su", INSTALLER.format(n=13, N="Trixie", c="trixie"))
out, stub = run(debian(13, "trixie"), apt13b, desktop=False, su=True)
open(SP + "/out/setup_debian13_su.out", "w").write(out)
lines = out.splitlines()
check(f"with su (no SUDO_USER, no sbin in its PATH): set up (exit {report(out, 'SETUP EXIT')}), nothing 'command "
      f"not found'", report(out, "SETUP EXIT") == "0" and "command not found" not in out)
check(f"...you found by the Pietato folder: signed in by yourself, the web page as you ({report(out, 'WEB USER')}, "
      f"{report(out, 'AUTOLOGIN')})", report(out, "WEB USER") == "[gpitest]"
      and report(out, "AUTOLOGIN") == "[--autologin gpitest]"
      and "==> Signing gpitest in by itself at start-up (sudo bash setup.sh --login undoes it)" in lines)

# ---- no sudo at all: what to run instead ----
nb = "/var/tmp/pietato-nosudo-test"          # (somewhere gpitest can reach, the scripts too: not this test's own
shutil.rmtree(nb, ignore_errors=True)        #  folder, nor perhaps the Pietato folder)
os.makedirs(nb + "/bin")
os.chmod(nb, 0o755)
for tool in ("bash", "id"):
    os.symlink(shutil.which(tool), f"{nb}/bin/{tool}")
for name in ("setup.sh", "stop.sh", "start.sh", "uninstall.sh"):
    shutil.copy(f"{ROOT}/{name}", f"{nb}/{name}")
    os.chmod(f"{nb}/{name}", 0o644)
    r = subprocess.run(["runuser", "-u", "gpitest", "--", "env", f"PATH={nb}/bin", "bash", f"{nb}/{name}"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=nb)
    check(f"{name} without sudo here: su -c ({r.stdout.strip()!r})", r.returncode == 1
          and r.stdout.strip() == f'Run it as root:  su -c "bash {name}"')
shutil.rmtree(nb, ignore_errors=True)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
