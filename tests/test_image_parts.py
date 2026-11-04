"""The image's own parts, on pretend roots (with Pietato's folder as new images have it, pietato, and as images
from before the renames have it, pie-tato and pitato): check.sh lets a clean image go and stops one with anything of anyone's in it
(each kind on its own); the pitato-user generator does nothing while Pitato's folder is where setup.sh put it, and
points the services (and the console's sign-in) at it once Raspberry Pi Imager has renamed the user; the first start
makes a Pi 4 or 5's N64, PSP and DS folders (not a Zero's), once."""
import os, shutil, subprocess, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
IMG = sys.argv[1] if len(sys.argv) > 1 else ROOT + "/image"
T = SP + "/t_image_parts"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def write(path, text="", mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mode is not None:
        os.chmod(path, mode)


FOLDER = "pietato"


def clean_root(r, user="pi"):
    shutil.rmtree(r, ignore_errors=True)
    write(f"{r}/etc/passwd", f"root:x:0:0:root:/root:/bin/bash\n{user}:x:1000:1000:,,,:/home/{user}:/bin/bash\n")
    write(f"{r}/etc/shadow", f"root:*:19000:0:99999:7:::\n{user}:!*:19000:0:99999:7:::\ndaemon:*:19000::::::\n")
    write(f"{r}/etc/hostname", "pietato\n")
    write(f"{r}/etc/machine-id", "")
    os.makedirs(f"{r}/etc/NetworkManager/system-connections")
    os.makedirs(f"{r}/etc/ssh")
    write(f"{r}/etc/ssh/sshd_config", "# defaults\n")
    write(f"{r}/boot/firmware/config.txt", "[all]\n")
    write(f"{r}/boot/firmware/cmdline.txt", "console=tty1 root=PARTUUID=x init=/usr/lib/raspberrypi-sys-mods/firstboot\n")
    for f in ("streams.txt", "radio.txt", "finance.txt", "fonts/OFL.txt"):
        write(f"{r}/home/{user}/{FOLDER}/static/{f}", "# starting settings\n")
    write(f"{r}/home/{user}/{FOLDER}/.git/config", '[remote "origin"]\n\turl = https://github.com/frogCaller/pietato.git\n')
    write(f"{r}/var/lib/pitato/installed-commit", "0" * 40 + "\n")
    os.makedirs(f"{r}/root")


def run_check(r):
    p = subprocess.run(["bash", f"{IMG}/check.sh", r], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


for FOLDER in ("pietato", "pie-tato", "pitato"):
    print(f"== the folder: {FOLDER}", flush=True)
    R = T + "/root"
    clean_root(R)
    rc, out = run_check(R)
    check(f"check.sh: a clean image goes ({rc}: {out.strip().splitlines()[-1]})", rc == 0 and "found:" not in out)

    LEAKS = [
        ("a saved WiFi network", lambda r: write(f"{r}/etc/NetworkManager/system-connections/home.nmconnection",
                                                 "[wifi-security]\npsk=hunter2\n")),
        ("WiFi in wpa_supplicant", lambda r: write(f"{r}/etc/wpa_supplicant/wpa_supplicant.conf",
                                                   'network={\n ssid="x"\n psk="hunter2"\n}\n')),
        ("Imager's first-start file", lambda r: write(f"{r}/boot/firmware/firstrun.sh", "#!/bin/bash\n")),
        ("Imager's user and password", lambda r: write(f"{r}/boot/firmware/userconf.txt", "pi:$6$hash\n")),
        ("SSH turned on in boot", lambda r: write(f"{r}/boot/firmware/ssh", "")),
        ("cloud-init's user-data", lambda r: write(f"{r}/boot/firmware/user-data", "#cloud-config\n")),
        ("an SSH host key", lambda r: write(f"{r}/etc/ssh/ssh_host_ed25519_key", "KEY")),
        ("someone's SSH key", lambda r: write(f"{r}/home/pi/.ssh/id_ed25519", "KEY")),
        ("root's authorized keys", lambda r: write(f"{r}/root/.ssh/authorized_keys", "ssh-ed25519 AAAA")),
        ("a password", lambda r: write(f"{r}/etc/shadow", "root:*:1::::::\npi:$6$salt$hash:1::::::\n")),
        ("an empty password", lambda r: write(f"{r}/etc/shadow", "root:*:1::::::\npi::1::::::\n")),
        ("Home Assistant's token", lambda r: write(f"{r}/home/pi/{FOLDER}/static/homeassistant.txt", "token = eyJ\n")),
        ("Pi-hole's password", lambda r: write(f"{r}/home/pi/{FOLDER}/static/pihole.txt", "password = x\n")),
        ("a bot's server", lambda r: write(f"{r}/home/pi/{FOLDER}/static/bot.txt", "server = 192.168.1.5\n")),
        ("Plex's sign-in", lambda r: write(f"{r}/var/lib/pitato/plex.json", '{"token": "x"}')),
        ("Pitato's saved state", lambda r: write(f"{r}/var/lib/pitato/state.json", "{}")),
        ("Pitato's cache", lambda r: os.makedirs(f"{r}/var/cache/pitato")),
        ("a shell history", lambda r: write(f"{r}/home/pi/.bash_history", "ls\n")),
        ("root's python history", lambda r: write(f"{r}/root/.python_history", "1+1\n")),
        ("git credentials", lambda r: write(f"{r}/home/pi/.git-credentials", "https://u:t@github.com\n")),
        ("a token in Pitato's git settings", lambda r: write(f"{r}/home/pi/{FOLDER}/.git/config",
            '[http "https://github.com/"]\n\textraheader = AUTHORIZATION: basic eDp4\n')),
        ("a token in Pitato's remote", lambda r: write(f"{r}/home/pi/{FOLDER}/.git/config",
            '[remote "origin"]\n\turl = https://x-access-token:abc@github.com/frogCaller/pitato.git\n')),
        ("a machine-id", lambda r: write(f"{r}/etc/machine-id", "0123456789abcdef0123456789abcdef\n")),
    ]
    for what, put in LEAKS:
        clean_root(R)
        put(R)
        rc, out = run_check(R)
        check(f"...{what}: stopped ({[l.strip() for l in out.splitlines() if 'found' in l]})",
              rc != 0 and "found:" in out and "Not let go" in out)

    # the generator: Imager renamed pi to bob
    GEN = f"{IMG}/pitato-user"


    def unit_root(r, folder_user):
        clean_root(r, folder_user)
        write(f"{r}/etc/systemd/system/pitato.service",
              f'[Service]\nEnvironment="PITATO_STATIC=/home/pi/{FOLDER}/static"\nExecStart=/usr/bin/python3 x\n')
        write(f"{r}/etc/systemd/system/pitato-web.service",
              f'[Service]\nUser=pi\nWorkingDirectory=/home/pi\nEnvironment="PITATO_STATIC=/home/pi/{FOLDER}/static"\n')
        write(f"{r}/etc/systemd/system/getty@tty1.service.d/autologin.conf",
              "[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM\n")
        os.chown(f"{r}/home/{folder_user}/{FOLDER}", 1000, 1000)


    def gen(r):
        out = T + "/gen"
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        p = subprocess.run(["sh", GEN, out, out + "-early", out + "-late"], env=dict(os.environ, PITATO_ROOT=r),
                           capture_output=True, text=True)
        files = {}
        for d, _, fs in os.walk(out):
            for f in fs:
                files[os.path.relpath(os.path.join(d, f), out)] = open(os.path.join(d, f)).read()
        return p.returncode, files


    unit_root(R, "pi")
    rc, files = gen(R)
    check(f"the generator: Pitato's folder where setup.sh put it, nothing to do ({rc}, {sorted(files)})",
          rc == 0 and files == {})
    unit_root(R, "bob")
    rc, files = gen(R)
    print(files)
    check("...the user renamed (bob, his home moved): the services pointed at the folder now, as him",
          rc == 0 and files.get("pitato.service.d/zz-pitato-user.conf") ==
          f'[Service]\nEnvironment="PITATO_STATIC=/home/bob/{FOLDER}/static"\n'
          and files.get("pitato-web.service.d/zz-pitato-user.conf") ==
          f'[Service]\nUser=bob\nWorkingDirectory=/home/bob\nEnvironment="PITATO_STATIC=/home/bob/{FOLDER}/static"\n')
    check("...and the console signs bob in (after autologin.conf, so it's what counts)",
          files.get("getty@tty1.service.d/zz-pitato-user.conf") ==
          "[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin bob --noclear %I $TERM\n"
          and sorted(["autologin.conf", "zz-pitato-user.conf"])[-1] == "zz-pitato-user.conf")
    os.remove(f"{R}/etc/systemd/system/getty@tty1.service.d/autologin.conf")
    rc, files = gen(R)
    check("...a password at start-up asked for (setup.sh --login): left so", rc == 0
          and "getty@tty1.service.d/zz-pitato-user.conf" not in files and "pitato.service.d/zz-pitato-user.conf" in files)
    shutil.rmtree(f"{R}/home/bob/{FOLDER}")
    rc, files = gen(R)
    check("...no Pietato folder at all: nothing", rc == 0 and files == {})

    # the first start
    FB = f"{IMG}/pitato-firstboot"
    for model, want in (("Raspberry Pi 5 Model B Rev 1.0", ["n64", "nds", "psp"]),
                         ("Raspberry Pi Zero 2 W Rev 1.0", [])):
        clean_root(R)
        os.makedirs(f"{R}/home/pi/Games/gb")
        os.chown(f"{R}/home/pi/{FOLDER}", 1000, 1000)
        write(T + "/model", model + "\0")
        p = subprocess.run(["sh", FB], env=dict(os.environ, PITATO_ROOT=R, PITATO_MODEL_FILE=T + "/model"),
                           capture_output=True, text=True)
        made = sorted(set(os.listdir(f"{R}/home/pi/Games")) - {"gb"})
        owners = {os.stat(f"{R}/home/pi/Games/{s}").st_uid for s in made}
        check(f"the first start on a {model.split(' Rev')[0]}: {made or 'no'} more game folders, the user's "
              f"({p.returncode}{p.stderr.strip()})", p.returncode == 0 and made == want and owners <= {1000}
              and os.path.exists(f"{R}/var/lib/pitato/image-firstboot-done"))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
