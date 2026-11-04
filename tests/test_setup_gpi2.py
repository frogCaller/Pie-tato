"""setup.sh and the GPi Case 2 (a Compute Module 4): the real setup.sh, start to end, in a mount namespace
(setupspin/full/inner.sh), from Bookworm's own config.txt. On a CM4 it asks about the GPi Case 2 (not the 2W); yes:
config.txt then has, as the firmware reads it on a CM4 (each part worked out here as it would: [gpio18=0] the case's
screen, [gpio18=1] the dock's TV), the case's screen (RetroFlag's settings for it, drawn by the firmware alone, no
KMS or fkms; the 3D chip on by an overlay of its own; the Pi's own sound off; its pins set through the LEDs' node, as
RetroFlag's overlay sets them, leaving GPIO 18, 19, 26 and 27 alone) or the TV (KMS, the dock's HDMI taken as plugged
in), and either way the power switch, the dock's pin read low unless it's high, and the case's USB on (once). --update
keeps it; --image --gpi2 makes it for an image; no: none of it, KMS as it was. RetroFlag's own patch there before: its
lines go, fkms too. The case's screen set up by hand (RetroFlag's dpi24 overlay under another name, which takes the
power switch's pins): asked, yes is the answer unless you say; --gpi2 --update puts the case's settings in place of
those, --update alone leaves them be. A Pi Zero is asked about the 2W, as before."""
import os, pty, re, select, shutil, signal, subprocess, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
F = SP + "/setupspin/full"
ROOT = os.environ.get("PITATO_ROOT", ROOT)
T = SP + "/t_setup_gpi2"
ok_all = []
os.environ["GIT_ALLOW_PROTOCOL"] = "file"    # (the emulators' sources not fetched, so not built: what's looked at here
                                             # is the case's settings, and a build takes setup.sh past run's timeout)


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


shutil.rmtree(T, ignore_errors=True)
os.makedirs(T)
shutil.rmtree(F + "/repo", ignore_errors=True)
shutil.copytree(ROOT, F + "/repo", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
CM4 = "Raspberry Pi Compute Module 4 Rev 1.1\x00"
ZERO = "Raspberry Pi Zero 2 W Rev 1.0\x00"
BOOKWORM = """# For more options and information see
# http://rptl.io/configtxt
dtparam=audio=on
camera_auto_detect=1
display_auto_detect=1
auto_initramfs=1
dtoverlay=vc4-kms-v3d
max_framebuffers=2
disable_fw_kms_setup=1
arm_64bit=1
disable_overscan=1
arm_boost=1

[cm4]
# Enable host mode on the 2711 built-in XHCI USB controller.
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
"""
RETROFLAG = """dtparam=audio=off
display_rotate=0
dtoverlay=dpi24
framebuffer_width=640
framebuffer_height=480
enable_dpi_lcd=1
display_default_lcd=1
dpi_group=2
dpi_mode=87
dpi_output_format=0x00016
hdmi_timings=640 0 41 40 41 480 0 18 9 18 0 0 0 60 0 24000000 1   #80hz
[pi4]
dtoverlay=vc4-fkms-v3d
max_framebuffers=2
[all]
overscan_scale=1
dtoverlay=dwc2,dr_mode=host
"""
# the case's screen set up by hand on Bookworm's own: KMS off, RetroFlag's dpi24 overlay under another name
HAND = BOOKWORM.replace("dtoverlay=vc4-kms-v3d\n", "#dtoverlay=vc4-kms-v3d\n") + """# GPi Case 2 screen (needs gpi2-dpi24.dtbo in the overlays folder)
dtoverlay=gpi2-dpi24
enable_dpi_lcd=1
display_default_lcd=1
dpi_group=2
dpi_mode=87
dpi_output_format=0x00016
hdmi_timings=640 0 41 40 41 480 0 18 9 18 0 0 0 60 0 24000000 1
framebuffer_width=640
framebuffer_height=480
"""
CASE_OVERLAYS = ["gpio-shutdown", "gpicase2-dpi", "gpicase2-3d"]   # (as the firmware reads them, out of the dock)


def run(args, model=CM4, config=BOOKWORM, answers=None, git=False, timeout=900):
    """setup.sh with these options on a Pi of this model, from this config.txt: on a terminal of its own, each question
    in answers ([(its words, the answer)]) answered as it comes up; with answers None, no terminal (an update's)."""
    for f in ("hold.log", "stub.log"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    with open(T + "/model", "w") as f:
        f.write(model)
    with open(T + "/config.txt", "w") as f:
        f.write(config)
    env = dict(os.environ, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", SETUP_ARGS=args or " ",
               CONFIG_INIT=T + "/config.txt", PITATO_MODEL_FILE=T + "/model")
    if git:
        env["SETUP_GIT"] = "1"
    env.pop("GIT_TERMINAL_PROMPT", None)
    if answers is None:
        env["SETUP_STDIN"] = "/dev/null"
        p = subprocess.run(["unshare", "-m", "bash", F + "/inner.sh"], env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        return p.stdout + p.stderr
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("unshare", ["unshare", "-m", "bash", F + "/inner.sh"], env)
    out, pos, asked, t0 = b"", 0, 0, time.monotonic()
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
            while asked < len(answers) and text.find(answers[asked][0], pos) >= 0:
                pos = text.find(answers[asked][0], pos) + 1
                time.sleep(0.2)
                os.write(fd, answers[asked][1])
                asked += 1
    for _ in range(100):
        done, _ = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        time.sleep(0.1)
    else:
        os.killpg(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    os.close(fd)
    return out.decode("utf-8", "replace").replace("\r\n", "\n")


HA, REBOOT = ("Home Assistant address", b"\n"), ("Reboot now?", b"n\n")


def report(out, key):
    m = re.search(rf"^{re.escape(key)}: \[(.*)\]$", out, re.M) or re.search(rf"^{re.escape(key)}: (.*)$", out, re.M)
    return m.group(1) if m else None


def config_of(out):
    return (report(out, "CONFIG") or "").replace("|", "\n")


def effective(config, gpio18, board=("cm4", "pi4")):
    """config.txt as the firmware reads it on this board, with GPIO 18 so: (overlays in order, {setting: value}).
    [all] ends every filter; a model filter ([pi4], [cm4]...) holds for this board or not; [gpioN=V] holds when
    the pin's so; filters of a kind replace each other, of different kinds both hold."""
    model = gpio = None
    overlays, settings = [], {}
    for raw in config.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"\[(.+)\]", line)
        if m:
            f = m.group(1)
            if f == "all":
                model = gpio = None
            elif re.fullmatch(r"gpio(\d+)=([01])", f):
                gpio = f
            else:
                model = f
            continue
        if model is not None and model not in board:
            continue
        if gpio is not None:
            pin, val = re.fullmatch(r"gpio(\d+)=([01])", gpio).groups()
            if int(pin) != 18 or int(val) != gpio18:
                continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key == "dtoverlay":
            overlays.append(value.split(",")[0].strip())
        elif key == "dtparam":
            k, _, v = value.partition("=")
            settings["dtparam:" + k.strip()] = v.strip()
        else:
            settings[key] = value.strip()
    return overlays, settings


def pins(dts):
    m = re.search(r"brcm,pins = <([^>]*)>", dts or "")
    return [int(x, 16) if x.startswith("0x") else int(x) for x in m.group(1).split()] if m else []


# ---- a CM4: asked about the GPi Case 2, yes ---------------------------------------------------------------------------
out = run("", answers=[("Is this Pi in a RetroFlag GPi Case", b"y\n"), HA, REBOOT])
open(T + "/yes.out", "w").write(out)
cfg = config_of(out)
check(f"a CM4: asked about the GPi Case 2 (no unless you say: it's often on a board of its own), not the 2W; yes: "
      f"set up for it (exit {report(out, 'SETUP EXIT')})",
      "Is this Pi in a RetroFlag GPi Case 2? [y/N]" in out and "GPi Case 2W?" not in out
      and "Setting up for the GPi Case 2: its screen (or a TV, in its dock), sound and buttons." in out
      and report(out, "SETUP EXIT") == "0")
check(f"...its overlays built ({report(out, 'GPI OVERLAY')})",
      report(out, "GPI OVERLAY").split() == ["gpicase2-3d.dtbo", "gpicase2-dpi.dtbo", "gpicase2-tv.dtbo"])
d3 = (report(out, "DTS gpicase2-3d") or "").replace("|", "\n")
check("...the 3D chip's: on, on its own (a Pi 4's, the CM4's), nothing else", 'v3d = "/fragment@0:target:0"' in d3
      and 'status = "okay";' in d3 and 'compatible = "brcm,bcm2711";' in d3 and "fragment@1" not in d3
      and "disabled" not in d3)
tvdts = (report(out, "DTS gpicase2-tv") or "").replace("|", "\n")
check("...the TV's: the dock's HDMI taken as plugged in under KMS (vc4.force_hotplug, added to the kernel's command line)",
      'bootargs = "vc4.force_hotplug=1";' in tvdts and 'target-path = "/chosen";' in tvdts)
dts = report(out, "DTS gpicase2-dpi").replace("|", "\n")
ps = pins(dts)
check(f"...the screen's pins (RGB666 on 0-9, 12-17, 20-25), not 18 (the dock), 19, 26 or 27 (the power switch): {ps}",
      set(range(0, 10)) | set(range(12, 18)) | set(range(20, 26)) <= set(ps) and not {18, 19, 26, 27} & set(ps)
      and "brcm,function = <0x06>" in dts)
check("...set through the LEDs' node, as RetroFlag's own overlay sets them (there whatever draws the screen); "
      "nothing else of its, nothing turned off", 'leds = "/fragment@0:target:0"' in dts
      and 'gpio = "/fragment@1:target:0"' in dts and "fragment@2" not in dts and "fb =" not in dts
      and "vc4 =" not in dts and "disabled" not in dts)
lcd_o, lcd = effective(cfg, 0)
tv_o, tv = effective(cfg, 1)
print("   case's screen:", lcd_o, {k: v for k, v in lcd.items() if k in (
    "enable_dpi_lcd", "hdmi_timings", "dtparam:audio", "dpi_output_format", "otg_mode", "gpio")})
print("   the TV:       ", tv_o, {k: v for k, v in tv.items() if k in ("enable_dpi_lcd", "hdmi_force_hotplug", "dtparam:audio")})
check("out of the dock (GPIO 18 low): the case's screen, RetroFlag's settings for it",
      lcd.get("enable_dpi_lcd") == "1" and lcd.get("display_default_lcd") == "1" and lcd.get("dpi_group") == "2"
      and lcd.get("dpi_mode") == "87" and lcd.get("dpi_output_format") == "0x00016"
      and lcd.get("hdmi_timings") == "640 0 41 40 41 480 0 18 9 18 0 0 0 60 0 24000000 1"
      and lcd.get("framebuffer_width") == "640" and lcd.get("framebuffer_height") == "480")
check(f"...drawn by the firmware alone (no KMS, no fkms), its pins' overlay, the 3D chip's for N64, PSP and "
      f"Dreamcast games, the power switch's ({lcd_o})", lcd_o == CASE_OVERLAYS)
check("...the Pi's own sound off: the case's (USB) is the one", lcd.get("dtparam:audio") == "off")
check(f"in the dock (GPIO 18 high): the TV, as any Pi on HDMI: KMS, the TV taken as there, none of the case's "
      f"screen ({tv_o})",
      tv_o.count("vc4-kms-v3d") == 1 and "gpicase2-tv" in tv_o and "gpicase2-tv" not in lcd_o
      and "vc4-fkms-v3d" not in tv_o and "gpicase2-dpi" not in tv_o and "gpicase2-3d" not in tv_o
      and "enable_dpi_lcd" not in tv and tv.get("dtparam:audio") == "on" and tv.get("hdmi_force_hotplug") == "1")
for o, st, where in ((lcd_o, lcd, "the case's screen"), (tv_o, tv, "the TV")):
    check(f"...{where}: the power switch, the dock's pin pulled low, the case's USB on (Bookworm's own, once)",
          "gpio-shutdown" in o and st.get("gpio") is not None and st.get("otg_mode") == "1")
check("...gpio lines: 18 in, pulled low; 27 held high", "gpio=18=ip,pd" in cfg and "gpio=27=op,dh" in cfg
      and cfg.count("otg_mode=1") == 1)
check("...fkms nowhere", "fkms" not in cfg)
check("...Bookworm's KMS line kept (commented), to come back without the case", "#dtoverlay=vc4-kms-v3d" in cfg)
check("...nothing for the 2W", "audremap" not in cfg and "gpicase-dpi\n" not in cfg + "\n"
      and "19200000" not in cfg)
check("All set, reboot to apply", "All set. Reboot to apply the screen and audio settings." in out)

# ---- --update: as it was, and twice the same ------------------------------------------------------------------------
out2 = run("--update", config=cfg + "\n", git=True)
cfg2 = config_of(out2)
asked = [a for a in ("Is this Pi in", "Reboot now?") if a in out2]
check(f"--update: no questions ({asked}), the GPi Case 2 still (exit {report(out2, 'SETUP EXIT')})", not asked
      and "Setting up for the GPi Case 2:" in out2 and report(out2, "SETUP EXIT") == "0")
check("...its part of config.txt the same, not twice", cfg2.count("# >>> gpi-case setup >>>") == 1
      and effective(cfg2, 0) == effective(cfg, 0) and effective(cfg2, 1) == effective(cfg, 1)
      and cfg2.count("otg_mode=1") == 1)

# ---- no: none of it ----------------------------------------------------------------------------------------------------
out3 = run("", config=cfg + "\n", answers=[("Is this Pi in a RetroFlag GPi Case", b"n\n"), HA, REBOOT])
open(T + "/no.out", "w").write(out3)
cfg3 = config_of(out3)
o3, s3 = effective(cfg3, 0)
check(f"set up again, no: none of the case's settings, KMS back ({o3})",
      "Is this Pi in a RetroFlag GPi Case 2? [Y/n]" in out3
      and "gpi-case setup" not in cfg3 and o3 == ["vc4-kms-v3d"] and "enable_dpi_lcd" not in s3
      and effective(cfg3, 1)[0] == ["vc4-kms-v3d"])

# ---- a CM4 on a board of its own: Enter is no ------------------------------------------------------------------------
out3b = run("", answers=[("Is this Pi in a RetroFlag GPi Case", b"\n"), HA, REBOOT])
check("a CM4, Enter at the question: no case, HDMI as it was", "Setting up for a screen on HDMI" in out3b
      and "gpi-case setup" not in config_of(out3b) and effective(config_of(out3b), 0)[0] == ["vc4-kms-v3d"])

# ---- Bookworm's own USB line taken out, a CM5's still there: the case's USB turned on all the same ------------------
nousb = BOOKWORM.replace("otg_mode=1\n", "")
out3c = run("--gpi2", config=nousb, answers=[HA, REBOOT])
cfg3c = config_of(out3c)
check("Bookworm's [cm4] otg_mode taken out (a CM5's dwc2 line still there): the case's USB on in its own part",
      effective(cfg3c, 0)[1].get("otg_mode") == "1" and effective(cfg3c, 1)[1].get("otg_mode") == "1"
      and "dwc2" not in effective(cfg3c, 0)[0])

# ---- an image: --image --gpi2 ------------------------------------------------------------------------------------------
out4 = run("--image --gpi2", model="", git=True)
cfg4 = config_of(out4)
check(f"--image --gpi2: no questions, the GPi Case 2's settings (exit {report(out4, 'SETUP EXIT')})",
      "Is this Pi in" not in out4 and "Setting up for the GPi Case 2:" in out4 and report(out4, "SETUP EXIT") == "0"
      and effective(cfg4, 0)[0] == effective(cfg, 0)[0] and effective(cfg4, 1)[0] == effective(cfg, 1)[0])
out5 = run("--image --gpi", model=CM4, git=True)
check("--image --gpi (built on a CM4, even): the 2W's, as images always had",
      "Setting up for the GPi Case 2W: its screen, speaker and buttons." in out5 and report(out5, "SETUP EXIT") == "0"
      and "gpicase-dpi" in config_of(out5) and "gpicase2-dpi" not in config_of(out5))

# ---- RetroFlag's patch there before ------------------------------------------------------------------------------------
out6 = run("--gpi2", config=RETROFLAG, answers=[HA, REBOOT])
cfg6 = config_of(out6)
lo, ls = effective(cfg6, 0)
to, ts = effective(cfg6, 1)
check(f"RetroFlag's patch there before: its screen lines and fkms out; ours alone (the case: {lo}; the TV: {to})",
      [o for o in lo if o != "dwc2"] == CASE_OVERLAYS and not re.search(r"^\s*dtoverlay=dpi24", cfg6, re.M)
      and "fkms" not in cfg6 and to.count("vc4-kms-v3d") == 1
      and cfg6.count("enable_dpi_lcd") == 1 and cfg6.count("hdmi_timings") == 1)
check("...its USB line (dwc2) kept, so no otg_mode added", "dtoverlay=dwc2,dr_mode=host" in cfg6
      and "otg_mode" not in cfg6)

# ---- the case's screen set up by hand: RetroFlag's dpi24 overlay under another name (it takes the power switch's pins) ---
out10 = run("", config=HAND, answers=[("Is this Pi in a RetroFlag GPi Case", b"\n"), HA, REBOOT])
open(T + "/hand.out", "w").write(out10)
cfg10 = config_of(out10)
o10 = effective(cfg10, 0)[0]
check(f"the case's screen set up by hand: asked, and yes unless you say (Enter: yes), set up for the case "
      f"(exit {report(out10, 'SETUP EXIT')})", "Is this Pi in a RetroFlag GPi Case 2? [Y/n]" in out10
      and "Setting up for the GPi Case 2: its screen (or a TV, in its dock), sound and buttons." in out10
      and report(out10, "SETUP EXIT") == "0")
check(f"...its lines gone (the overlay that takes the power switch's pins, and its comment); ours alone, once ({o10})",
      "gpi2-dpi24" not in cfg10 and "# GPi Case 2 screen" not in cfg10 and o10 == CASE_OVERLAYS
      and cfg10.count("enable_dpi_lcd") == 1 and cfg10.count("hdmi_timings") == 1
      and cfg10.count("framebuffer_width") == 1 and cfg10.count("otg_mode=1") == 1
      and effective(cfg10, 0) == effective(cfg, 0) and effective(cfg10, 1) == effective(cfg, 1))
out11 = run("--gpi2 --update", config=HAND, git=True)
cfg11 = config_of(out11)
check(f"...--gpi2 --update: the same, with no questions (exit {report(out11, 'SETUP EXIT')})",
      "Is this Pi in" not in out11 and "Setting up for the GPi Case 2:" in out11 and report(out11, "SETUP EXIT") == "0"
      and "gpi2-dpi24" not in cfg11 and effective(cfg11, 0) == effective(cfg10, 0)
      and effective(cfg11, 1) == effective(cfg10, 1))
out12 = run("--update", config=HAND, git=True)
cfg12 = config_of(out12)
check(f"...--update alone: left as it is, as it was set up (exit {report(out12, 'SETUP EXIT')})",
      "Is this Pi in" not in out12 and "Setting up for a screen on HDMI" in out12 and report(out12, "SETUP EXIT") == "0"
      and cfg12.strip() == HAND.strip())
out13 = run("", config=HAND, answers=[("Is this Pi in a RetroFlag GPi Case", b"n\n"), HA, REBOOT])
check("...no: left as it is", "Setting up for a screen on HDMI" in out13 and config_of(out13).strip() == HAND.strip())

# ---- a Pi Zero: asked about the 2W, as before ---------------------------------------------------------------------------
out7 = run("", model=ZERO, config="[all]\ndtoverlay=vc4-kms-v3d\n",
           answers=[("Is this Pi in a RetroFlag GPi Case", b"y\n"), HA, REBOOT])
cfg7 = config_of(out7)
open(T + "/zero.out", "w").write(out7)
check("a Pi Zero 2 W: asked about the 2W, set up for it as before", "Is this Pi in a RetroFlag GPi Case 2W? [Y/n]" in out7
      and "Setting up for the GPi Case 2W: its screen, speaker and buttons." in out7
      and "dtoverlay=gpicase-dpi" in cfg7 and "hdmi_timings=640 0 1 1 20 480 0 1 1 2 0 0 0 60 0 19200000 1" in cfg7
      and "[gpio18" not in cfg7 and "GPi Case 2 (CM4)" not in cfg7)
out8 = run("--update", model=ZERO, config=cfg7 + "\n", git=True)
check("...--update: the 2W still", "Setting up for the GPi Case 2W" in out8 and "GPi Case 2 (CM4)" not in config_of(out8))
out9 = run("", model="Raspberry Pi 4 Model B Rev 1.5\x00", answers=[HA, REBOOT])
check("a Pi 4: not asked about either case", "Is this Pi in" not in out9 and "Setting up for a screen on HDMI" in out9)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
