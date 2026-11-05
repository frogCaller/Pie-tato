"""The real setup.sh, start to end, in a mount namespace (what it writes lands on tmpfs there: setupspin/full/inner.sh)
on a pretend screen: the moving line through PCSX ReARMed's download and build (a pretend source: no network for
GitHub's archives here, setupspin/full/bin/curl), the hold on shutting down let go before All set; then an error partway (apt-get update failing) and Ctrl+C during the build: it says it
stopped, lets go, and tidies up."""
import fcntl, os, pty, re, select, shutil, signal, struct, sys, termios, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
F = SP + "/setupspin/full"
ROOT = os.environ.get("PITATO_ROOT", ROOT)
ok_all = []
ONLY = sys.argv[1:]


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


shutil.rmtree(F + "/repo", ignore_errors=True)
shutil.copytree(ROOT, F + "/repo", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
PROMPTS = [("Home Assistant address", b"\n"), ("Reboot now?", b"n\n")]
GONE = ("A camera's address", "Camera tab", "No cameras yet", "Finance tab", "The Finance tab shows",
        "Keeping your existing")             # (the camera question and the Finance tab's words: gone)


def run(mode, timeout=1800, prompts=PROMPTS):
    for f in ("hold.log", "stub.log"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    env = dict(os.environ, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", PIETATO_SETUP_UI="plain")
    env.pop("GIT_TERMINAL_PROMPT", None)
    if mode == "aptfail":
        env["APT_FAIL"] = "1"
    if mode.startswith("update"):                      # (as Update software runs it: no terminal to ask on)
        env.update(SETUP_ARGS="--update", SETUP_STDIN="/dev/null", SETUP_GIT="1")
        if mode == "update_gpi":
            env["GPI_BLOCK"] = "1"
    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        os.execvpe("unshare", ["unshare", "-m", "bash", F + "/inner.sh"], env)
    out, pos, asked, stopped, t0 = b"", 0, 0, False, time.monotonic()
    while time.monotonic() - t0 < timeout:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            out += chunk
            text = out.decode("utf-8", "replace")
            while asked < len(prompts) and text.find(prompts[asked][0], pos) >= 0:
                pos = text.find(prompts[asked][0], pos) + 1
                time.sleep(0.2)
                os.write(fd, prompts[asked][1])
                asked += 1
            if mode == "ctrlc" and not stopped and re.search(r"\r  [|/\\-] Building  0:0[3-9]", text):
                os.write(fd, b"\x03")
                stopped = True
    took = time.monotonic() - t0
    done, st = os.waitpid(pid, os.WNOHANG)
    for _ in range(50):                                # (its screen closed: a moment for it to end)
        if done:
            break
        time.sleep(0.1)
        done, st = os.waitpid(pid, os.WNOHANG)
    if not done:                                       # (stuck: everything it started goes)
        print(f"(still going after {timeout} s: stopped)")
        os.killpg(pid, signal.SIGKILL)
        st = os.waitpid(pid, 0)[1]
    os.close(fd)
    return out.decode("utf-8", "replace"), st, took


def frames(out):
    return [f.replace("\x1b[K", "") for f in re.split(r"[\r\n]+", out) if f.replace("\x1b[K", "").strip()]


def report(fs, key):
    return next((f.split(": ", 1)[1] for f in fs if f.startswith(key + ": ")), None)


def holds():
    try:
        return open(F + "/hold.log").read().splitlines()
    except OSError:
        return []


STOPPED = "setup.sh stopped before it was done. Run  sudo bash setup.sh  again to finish."

# ---- start to end ----
if not ONLY or "ok" in ONLY:
    out, st, took = run("ok")
    open(F + "/ok.out", "w").write(out)
    fs = frames(out)
    print(f"(start to end: {took:.0f} s)")
    check("first: it takes a while, so leave the Pi on until All set",
          "The first time takes a while: an hour or more on a Pi 4, as it builds the game emulators." in fs
          and "Leave the Pi on until it says All set." in fs
          and fs.index("Leave the Pi on until it says All set.") < fs.index("==> Installing packages"))
    check(f"no camera question and not a word about the Finance tab, its file made all the same; Home Assistant "
          f"still asked about ({report(fs, 'STATIC')})",
          not [w for w in GONE if w in out] and "Home Assistant address" in out
          and "finance.txt" in report(fs, "STATIC") and "camera.txt" not in report(fs, "STATIC"))
    i = next(k for k, f in enumerate(fs) if f.startswith("==> Building the PlayStation emulator"))
    part = fs[i:next((k for k in range(i + 1, len(fs)) if fs[k].startswith("==> ")), len(fs))]   # (to the next step)
    dl = [f for f in part if re.match(r"^  [|/\\-] Downloading  \d+:\d\d  Still working: leave the Pi on$", f)]
    bl = [f for f in part if re.match(r"^  [|/\\-] Building  \d+:\d\d  Still working: leave the Pi on$", f)]
    dn = [f for f in part if re.fullmatch(r"  (Downloading|Building): done \(took \d+:\d\d\)", f)]
    check(f"the PlayStation emulator: downloaded and built, a line moving all the while ({len(dl)} and {len(bl)} "
          f"redraws, {dn})", dl and len(bl) >= 12 and [d.split(":")[0].strip() for d in dn] == ["Downloading", "Building"])
    secs = [int(m.group(1)) * 60 + int(m.group(2)) for f in bl for m in [re.search(r"(\d+):(\d\d)  Still", f)]]
    took_b = re.search(r"took (\d+):(\d\d)", dn[-1])
    check(f"...its clock counting up, to about what it took ({secs[0]} s ... {secs[-1]} s, {dn[-1]})",
          secs == sorted(secs) and 0 <= int(took_b.group(1)) * 60 + int(took_b.group(2)) - secs[-1] <= 2)
    check(f"...built and kept ({report(fs, 'CORES')}, {report(fs, 'VERSION')})",
          "pcsx_rearmed_libretro.so" in report(fs, "CORES") and len(report(fs, "VERSION")) == 42)
    check(f"...its folder in /var/tmp gone ({report(fs, 'VARTMP')})", report(fs, "VARTMP") == "[]")
    check("...the build's own output in its log, not on the screen", not any(".o " in f or "gcc" in f for f in fs))
    check("Bluetooth on, and no question about pairing: it says where to pair instead",
          "Pair Bluetooth controllers, keyboards, headphones and the rest in Settings > Bluetooth, or on the web page."
          in fs and not any("Pair a Bluetooth" in f for f in fs) and "==> Bluetooth" in fs)
    stub = open(F + "/stub.log").read().splitlines()
    check("...BlueALSA for headphones: installed, enabled, started",
          "apt-get install -y bluez-alsa-utils libasound2-plugin-bluez" in stub and "systemctl enable bluealsa" in stub
          and "systemctl restart bluealsa" in stub and not any("BlueALSA" in f for f in fs))
    check(f"...as the player only ({report(fs, 'BLUEALSA')})", report(fs, "BLUEALSA") ==
          "[# Pietato (setup.sh): sound to Bluetooth headphones and speakers, the Pi as the player|[Service]|"
          f"ExecStart=|ExecStart={F}/bin/bluealsa -p a2dp-source|]")
    k = fs.index("All set. Reboot to start.")
    check(f"All set at the end, and no word of stopping early ({fs[k - 1:k + 1]}, exit {report(fs, 'SETUP EXIT')})",
          STOPPED not in fs and report(fs, "SETUP EXIT") == "0")
    h = holds()
    check(f"held from the start, let go before All set ({h})", len(h) == 2 and h[0].startswith("held ")
          and "--what=shutdown:sleep:handle-power-key" in h[0] and h[1].startswith("let go "))
    check(f"...on Raspberry Pi OS (its os-release, Debian's: {report(fs, 'OS')})", report(fs, "OS") == "[debian]")
    check(f"...the services it'd start, as before ({report(fs, 'UNITS')})",
          report(fs, "UNITS") == "[bluealsa.service.d getty@tty1.service.d pitato-web.service pitato.service ]")
    check(f"...not a git clone: nothing noted for Update software ({report(fs, 'INSTALLED')})",
          report(fs, "INSTALLED") == "[]")

# ---- --update (System > Update software): no questions, as it was set up, no restart of its own ----
ASKS = ("Is this Pi in a RetroFlag", "Set the TV picture", "A camera's address", "Home Assistant address",
        "Reboot now?")
for mode in ("update", "update_gpi"):
    if ONLY and mode not in ONLY:
        continue
    out, st, took = run(mode, prompts=[])
    open(F + f"/{mode}.out", "w").write(out)
    fs = frames(out)
    print(f"({mode}: {took:.0f} s)")
    asked = [a for a in ASKS if a in out]
    check(f"--update ({mode}): no questions ({asked}), right to the end (exit {report(fs, 'SETUP EXIT')})",
          not asked and report(fs, "SETUP EXIT") == "0" and STOPPED not in fs and "All set." in " ".join(fs))
    if mode == "update":
        check("...set up as it was: a screen on HDMI (no GPi Case settings in config.txt)",
              any(f.startswith("Setting up for a screen on HDMI") for f in fs) and report(fs, "GPI OVERLAY") == "[]")
    else:
        check(f"...set up as it was: the GPi Case (its settings in config.txt) ({report(fs, 'GPI OVERLAY')})",
              "Setting up for the GPi Case 2W: its screen, speaker and buttons." in fs
              and "gpicase-dpi.dtbo" in report(fs, "GPI OVERLAY"))
    check("...Home Assistant left for later, and not a word about cameras or the Finance tab",
          "No Home Assistant yet: add it any time in its Settings, on the Pi or the web page." in fs and not [w for w in GONE if w in out])
    stub = open(F + "/stub.log").read().splitlines()
    check("...no restart of its own (Update software restarts the Pi after)",
          not any(s.startswith("reboot") for s in stub) and "systemctl restart pitato" not in stub)
    check(f"...what it put in, noted ({report(fs, 'INSTALLED')})",
          report(fs, "INSTALLED") == report(fs, "HEAD") and len(report(fs, "HEAD")) == 42)
    h = holds()
    check(f"...held while it worked, let go at the end ({len(h)})", len(h) == 2 and h[1].startswith("let go "))

# ---- an error partway ----
if not ONLY or "aptfail" in ONLY:
    out, st, took = run("aptfail")
    fs = frames(out)
    check(f"an error partway (apt-get update): it says it stopped ({fs[-7:-5]})",
          "E: no network (pretend)" in fs and STOPPED in fs and "All set. Reboot to start." not in fs
          and report(fs, "SETUP EXIT") not in (None, "0"))
    h = holds()
    check(f"...and lets go ({h})", len(h) == 2 and h[1].startswith("let go "))

# ---- Ctrl+C while it builds ----
if not ONLY or "ctrlc" in ONLY:
    out, st, took = run("ctrlc")
    open(F + "/ctrlc.out", "w").write(out)
    fs = frames(out)
    check(f"Ctrl+C while it builds: it says it stopped ({[f for f in fs if 'stopped' in f or 'EXIT' in f]})",
          STOPPED in fs and "All set. Reboot to start." not in fs and report(fs, "SETUP EXIT") == "130")
    check("...its moving line wiped first", re.search(r"\r\x1b\[K\r\nsetup\.sh stopped", out) is not None)
    check(f"...the half-built emulator's folder gone, nothing built ({report(fs, 'VARTMP')}, {report(fs, 'CORES')})",
          report(fs, "VARTMP") == "[]" and report(fs, "CORES") == "[]")
    h = holds()
    check(f"...and lets go ({h})", len(h) >= 2 and h[0].startswith("held ") and
          any(x.startswith(("let go ", "ended ")) for x in h[1:]))

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
