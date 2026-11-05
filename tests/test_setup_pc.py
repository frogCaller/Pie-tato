"""setup.sh on a PC (Ubuntu 24.04, Intel or AMD): the real setup.sh, start to end, in a mount namespace
(setupspin/full/inner.sh, PC_MODE: no config.txt or cmdline.txt), with no network for the emulators' sources (git
clone fails; PCSX ReARMed's is a pretend one). With Ubuntu's desktop: no GPi Case question, says it's setting up
this computer; every emulator tried (not "needs a Pi 4 or 5"), PCSX ReARMed built for a PC (platform unix); the
game folders for every system; Chromium from Ubuntu (chromium-browser: its snap); it starts in the terminal now
(multi-user.target) and says System > Desktop starts the desktop; the Loopback card's module from
linux-modules-extra when it isn't there; the desktop's PipeWire told to leave the Loopback card alone; BlueALSA left
out (PipeWire has Bluetooth's sound); config.txt and the GPi Case's overlays untouched. Without a desktop (Ubuntu
Server): none of the desktop's, BlueALSA in. An update: the start-up target left as it is."""
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


def run(desktop, update=False):
    for f in ("hold.log", "stub.log"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    env = dict(os.environ, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", PC_MODE="1",
               SETUP_STDIN="/dev/null" if update else SP + "/setupspin/pc_answers.txt",   # (Home Assistant: none; reboot: no)
               SETUP_GIT="1", EXTRA_BIN=SP + ("/setupspin/pcbin_desk" if desktop else "/setupspin/pcbin"),
               STUB_DEFAULT_TARGET="graphical.target" if desktop else "multi-user.target",
               SETUP_ARGS="--update" if update else "--no-gpi")
    if desktop:
        env["DESKTOP_DM"] = "1"
    env.pop("GIT_TERMINAL_PROMPT", None)
    env.pop("PITATO_MODEL_FILE", None)
    p = subprocess.run(["unshare", "-m", "bash", F + "/inner.sh"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=1800)
    out = p.stdout + p.stderr
    stub = open(F + "/stub.log").read().splitlines() if os.path.exists(F + "/stub.log") else []
    return out, stub


def report(out, key):
    m = re.search(rf"^{re.escape(key)}: (.*)$", out, re.M)
    return m.group(1) if m else None


# ---- with Ubuntu's desktop ----
out, stub = run(desktop=True)
open(SP + "/out/setup_pc_desktop.out", "w").write(out)
lines = out.splitlines()
check(f"a PC: no GPi Case question, it says it's setting up this computer (exit {report(out, 'SETUP EXIT')})",
      "RetroFlag" not in out and "Setting up this computer. Plug in any USB or Bluetooth game controller." in lines
      and report(out, "SETUP EXIT") == "0")
check(f"...on Ubuntu (this machine's os-release: {report(out, 'OS')})", report(out, "OS") == "[ubuntu]")
check("...and to leave the computer on (not the Pi)", "Leave the computer on until it says All set." in lines
      and "leave the Pi on" not in out.lower())
check(f"...the PlayStation emulator built for a PC ({report(out, 'CORES')}, {report(out, 'PCSX')})",
      "pcsx_rearmed_libretro.so" in (report(out, "CORES") or "") and report(out, "PCSX") == "[platform=unix ]")
for name, words in (("N64", "Mupen64Plus-Next"), ("PSP", "PPSSPP"), ("DS", "melonDS"), ("Dreamcast", "Flycast")):
    check(f"...the {name} emulator tried too, not left to a Pi 4 or 5 (no network here: it says it couldn't)",
          f"(Couldn't build {words}: " in out and f"({name} games need a Pi 4 or 5" not in out)
check("...achievements (rcheevos) tried too, on any computer (no network here: it says it couldn't)",
      "==> Building achievements (rcheevos): a minute or so" in out
      and "(Couldn't build rcheevos: games won't have achievements.)" in out)
for name, words in (("GameCube and Wii", "Dolphin"), ("PlayStation 2", "LRPS2")):
    check(f"...and the {name} emulator ({words}), a PC's alone: tried (no network here: it says it couldn't)",
          f"==> Building the {name} emulator ({words}): about 15 minutes" in out
          and f"(Couldn't build {words}: {name} games won't start.)" in out)
check(f"the game folders for every system ({report(out, 'GAMES')})",
      all(g in (report(out, "GAMES") or "").split() for g in ("gb", "ps1", "n64", "psp", "nds", "dc", "ps2", "gc", "wii")))
check("Chromium from Ubuntu (its snap, through chromium-browser), with cage",
      "apt-get install -y chromium-browser" in stub and any(s.startswith("apt-get install -y cage ") for s in stub)
      and "apt-get install -y chromium" not in stub)
check("it starts in the terminal now, with Pietato, instead of the desktop",
      "systemctl set-default multi-user.target" in stub
      and "==> This computer starts in Pietato now, not the desktop (System > Desktop starts the desktop)" in lines)
mods = [s for s in stub if s.startswith("apt-get install -y linux-modules-extra-")]
check(f"the Loopback card's module (not loaded here): from Ubuntu's linux-modules-extra ({mods})",
      mods == [f"apt-get install -y linux-modules-extra-{os.uname().release}"])
check(f"the desktop's PipeWire leaves the Loopback card alone ({report(out, 'WIREPLUMBER')})",
      report(out, "WIREPLUMBER") == "[./main.lua.d/51-pietato-loopback.lua ./wireplumber.conf.d/51-pietato-loopback.conf ]"
      and 'alsa_card.platform-snd_aloop.*' in (report(out, "WP LUA") or "")
      and '["device.disabled"] = true' in (report(out, "WP LUA") or ""))
check("BlueALSA left out: the desktop's PipeWire has Bluetooth's sound",
      "(PipeWire or PulseAudio has Bluetooth's sound on this computer: BlueALSA left out.)" in lines
      and not any("bluez-alsa" in s for s in stub))
check("at the end: All set, and how the desktop and Pietato go",
      "All set. Reboot to start." in lines
      and "This computer starts in Pietato. System > Desktop starts the desktop, and restarting comes back to Pietato."
      in lines)
check(f"no config.txt made or changed, no GPi Case overlays ({report(out, 'CONFIG')}, {report(out, 'GPI OVERLAY')})",
      report(out, "CONFIG") == "[]" and report(out, "GPI OVERLAY") == "[]")
check("Home Assistant asked about on this computer, not the Pi",
      "or later in its Settings, on the computer or the web page (easier for pasting the token)." in lines)

# ---- Ubuntu Server: no desktop ----
out, stub = run(desktop=False)
open(SP + "/out/setup_pc_server.out", "w").write(out)
lines = out.splitlines()
check(f"no desktop (Ubuntu Server): the start-up target left be, nothing said about a desktop (exit {report(out, 'SETUP EXIT')})",
      report(out, "SETUP EXIT") == "0" and not any("set-default" in s for s in stub)
      and "System > Desktop" not in out)
HAS_RFKILL = shutil.which("rfkill") is not None    # (this machine's own: setup.sh puts it in only where it isn't)
check("...rfkill put in where it isn't (Ubuntu Server's hasn't it: Pietato turns Bluetooth back on with it), and "
      f"nothing said about it{' (this machine has it: left be)' if HAS_RFKILL else ''}",
      ("apt-get install -y rfkill" in stub) != HAS_RFKILL and "rfkill" not in out)
check("...BlueALSA in, as on a Pi (no PipeWire here)", "apt-get install -y bluez-alsa-utils libasound2-plugin-bluez" in stub)
check(f"...nothing for a PipeWire that isn't here ({report(out, 'WIREPLUMBER')})", report(out, "WIREPLUMBER") == "[]")

# ---- an update, with the desktop ----
out, stub = run(desktop=True, update=True)
open(SP + "/out/setup_pc_update.out", "w").write(out)
check(f"an update: no questions, and the start-up target left as you have it (exit {report(out, 'SETUP EXIT')})",
      report(out, "SETUP EXIT") == "0" and not any("set-default" in s for s in stub)
      and "[Y/n]" not in out and "[y/N]" not in out)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
