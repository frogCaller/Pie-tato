#!/bin/bash
# Runs inside `unshare -m`: the real setup.sh, with what it writes (/usr/local, /etc/systemd/system, /var/tmp,
# /home, /boot, /var/lib/pitato) on tmpfs in this mount namespace only, apt-get, systemctl and reboot stood in for,
# and gpitest as the user who ran sudo. Then a report of what it left.
# SETUP_ARGS: its options (--no-gpi); SETUP_STDIN: what it reads instead of the terminal (an update's /dev/null);
# SETUP_GIT: the pitato folder a git clone; GPI_BLOCK: config.txt has the GPi Case's settings from before;
# CONFIG_INIT: a config.txt to start from; PITATO_MODEL_FILE: the Pi's model, as /proc/device-tree/model says it.
# PC_MODE: a PC (Ubuntu, Intel or AMD): no config.txt or cmdline.txt; DESKTOP_DM: with a desktop (display-manager.service).
# OS_RELEASE: an os-release of the test's own (Debian's, on a PC); APT_DIR: an /etc/apt of its own (its sources);
# AS_SU: run with su, as on Debian without sudo: no SUDO_USER, a PATH without sbin, the Pietato folder yours.
# Without PC_MODE, Raspberry Pi OS's os-release (Debian's) instead of this machine's (Ubuntu's).
# RCLOCAL_INIT: an rc.local to start from. AFTER: then these, one by one ("stop.sh|start.sh @display-manager|
# uninstall.sh --yes": each from the Pietato folder, with what's after @ running), with what's left after each.
set -e
W="${PIETATO_TEST_WORK:?}"
F="$W/setupspin/full"
mount --make-rprivate /
exec 9< "$W"            # (the test's own folder: still here after what's covered next, should it be in one of them)
for d in /usr/local /etc/systemd/system /var/tmp /home /boot /var/lib/pitato /etc/wireplumber; do
  mkdir -p "$d"
  mount -t tmpfs -o mode=755 tmpfs "$d"
done
if [ ! -d "$F" ]; then mkdir -p "$W" && mount --no-canonicalize --bind /proc/self/fd/9 "$W"; fi
exec 9<&-
OWN="//"                   # (the test's own folder's place in /var/tmp, if it's there: not something setup.sh left)
case "$W/" in /var/tmp/*) OWN="${W#/var/tmp/}"; OWN="${OWN%%/*}" ;; esac
mkdir -p /usr/local/bin /usr/local/lib /usr/local/share /usr/local/sbin /boot/overlays
chmod 1777 /var/tmp
cp /etc/modules "$F/modules" && mount --bind "$F/modules" /etc/modules
rm -rf "$F/pam.d" && cp -a /etc/pam.d "$F/pam.d" && mount --bind "$F/pam.d" /etc/pam.d   # (Chromium's PAM service)
if [ -n "$PC_MODE" ]; then            # (a PC: no config.txt, no cmdline.txt; maybe a desktop)
  if [ -n "$DESKTOP_DM" ]; then printf "[Unit]\nDescription=GNOME Display Manager (pretend)\n" > /etc/systemd/system/display-manager.service; fi
elif [ -n "$CONFIG_INIT" ]; then        # (a config.txt of the test's own: Bookworm's, say)
  cp "$CONFIG_INIT" /boot/config.txt
elif [ -n "$GPI_BLOCK" ]; then
  printf '[all]\n#dtoverlay=vc4-kms-v3d\n# >>> gpi-case setup >>>\ndtoverlay=gpicase-dpi\n# <<< gpi-case setup <<<\n' \
    > /boot/config.txt
else
  printf '[all]\ndtoverlay=vc4-kms-v3d\n' > /boot/config.txt
fi
if [ -z "$PC_MODE" ]; then echo "console=tty1 root=PARTUUID=1234 rootwait" > /boot/cmdline.txt; fi
if [ -n "$RCLOCAL_INIT" ]; then             # (an rc.local of the test's own, RetroFlag's safe-shutdown script in it: this
  cp "$RCLOCAL_INIT" /etc/rc.local          # machine's own, as sed -i can't replace a file mounted on its own; the test
fi                                          # takes it away again)
if [ -n "$OS_RELEASE" ]; then mount --bind "$OS_RELEASE" /etc/os-release; fi
if [ -n "$APT_DIR" ]; then mount --bind "$APT_DIR" /etc/apt; fi
if [ -z "$PC_MODE" ]; then mount --bind "$F/rpios-os-release" /etc/os-release; fi   # (a Pi: Raspberry Pi OS's, Debian's;
                                                                                   # a PC: this machine's, Ubuntu 24.04's)
mkdir -p /home/gpitest && chown gpitest:gpitest /home/gpitest
cp -a "$F/repo" /home/gpitest/pitato
if [ -n "$SETUP_GIT" ]; then
  export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1     # (this machine's own git settings left out: signing...)
  git -C /home/gpitest/pitato init -q
  git -C /home/gpitest/pitato add -A
  git -C /home/gpitest/pitato -c user.name=t -c user.email=t@example.com commit -qm test
  unset GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM
fi
export SUDO_USER=gpitest PATH="${EXTRA_BIN:+$EXTRA_BIN:}$F/bin:$F/../bin:$PATH"
if [ -n "$AS_SU" ]; then
  chown -R gpitest:gpitest /home/gpitest/pitato
  unset SUDO_USER
  PATH="$(echo "$PATH" | tr ':' '\n' | grep -v 'sbin$' | paste -sd: -)"
fi
trap 'echo "(inner: Ctrl+C)"' INT
rc=0
if [ -n "$SETUP_STDIN" ]; then
  bash /home/gpitest/pitato/setup.sh ${SETUP_ARGS:---no-gpi} < "$SETUP_STDIN" || rc=$?
else
  bash /home/gpitest/pitato/setup.sh ${SETUP_ARGS:---no-gpi} || rc=$?
fi
echo "SETUP EXIT: $rc"
echo "VARTMP: [$(ls -A /var/tmp | grep -vxF -- "$OWN" | tr '\n' ' ')]"
echo "CORES: [$(ls /usr/local/lib/libretro 2> /dev/null | tr '\n' ' ')]"
echo "VERSION: [$(cat /usr/local/lib/libretro/pcsx_rearmed.version 2> /dev/null)]"
echo "UNITS: [$(ls /etc/systemd/system | tr '\n' ' ')]"
echo "BLUEALSA: [$(tr '\n' '|' < /etc/systemd/system/bluealsa.service.d/pitato.conf 2> /dev/null)]"
echo "INSTALLED: [$(cat /var/lib/pitato/installed-commit 2> /dev/null)]"
echo "HEAD: [$(git -c safe.directory='*' -C /home/gpitest/pitato rev-parse HEAD 2> /dev/null)]"
echo "GPI OVERLAY: [$(ls /boot/overlays | tr '\n' ' ')]"
echo "STATIC: [$(ls /home/gpitest/pitato/static 2> /dev/null | tr '\n' ' ')]"
echo "GAMES: [$(ls /home/gpitest/Games 2> /dev/null | tr '\n' ' ')]"
echo "OS: [$(. /etc/os-release && echo "$ID")]"
echo "WEB USER: [$(sed -n 's/^User=//p' /etc/systemd/system/pitato-web.service 2> /dev/null)]"
echo "AUTOLOGIN: [$(grep -o -- '--autologin [^ ]*' /etc/systemd/system/getty@tty1.service.d/autologin.conf 2> /dev/null)]"
echo "CHROMIUM PAM: [$(tr '\n' '|' < /etc/pam.d/pietato-chromium 2> /dev/null)]"
if [ -n "$EXTRA_BIN" ]; then echo "PCSX: [$(cat /usr/local/lib/libretro/pcsx_rearmed_libretro.so 2> /dev/null | tr '\n' ' ')]"; fi
echo "CONFIG: [$(tr '\n' '|' < /boot/config.txt 2> /dev/null)]"
echo "WIREPLUMBER: [$(cd /etc/wireplumber 2> /dev/null && find . -type f | sort | tr '\n' ' ')]"
echo "WP LUA: [$(tr '\n' '|' < /etc/wireplumber/main.lua.d/51-pietato-loopback.lua 2> /dev/null)]"
for o in gpicase-dpi gpicase2-dpi gpicase2-3d gpicase2-tv; do
  if [ -f "/boot/overlays/$o.dtbo" ]; then echo "DTS $o: [$(dtc -q -I dtb -O dts "/boot/overlays/$o.dtbo" | tr '\n' '|')]"; fi
done
if [ -n "$AFTER" ]; then
  mkdir -p /home/gpitest/.cache/pitato/thumbs && : > /home/gpitest/.cache/pitato/thumbs/a.jpg   # (the web page's)
  mkdir -p /usr/local/lib/libretro && : > /usr/local/lib/libretro/other_libretro.so   # (one of your own, beside setup.sh's)
  : > /home/gpitest/Videos/mine.mp4
  IFS='|' read -ra steps <<< "$AFTER"
  for s in "${steps[@]}"; do
    cmd="${s%%@*}"; active=""
    case "$s" in *@*) active="${s#*@}" ;; esac
    echo "### $cmd" >> "$STUB_LOG"
    echo "=== $cmd"
    rc=0; STUB_ACTIVE="$active" bash -c "cd /home/gpitest/pitato && bash $cmd" < /dev/null || rc=$?
    echo "=== EXIT $cmd: $rc"
    echo "UNITS AFTER: [$(ls /etc/systemd/system | tr '\n' ' ')]"
    echo "LOCAL AFTER: [$(ls /usr/local/bin /usr/local/share /usr/local/lib 2> /dev/null | tr '\n' ' ')]"
    echo "CORES AFTER: [$(ls /usr/local/lib/libretro 2> /dev/null | tr '\n' ' ')]"
    echo "VARLIB AFTER: [$(ls -A /var/lib/pitato 2> /dev/null | tr '\n' ' ')]"
    echo "HOME AFTER: [$(ls /home/gpitest | tr '\n' ' ')] [$(ls /home/gpitest/Videos | tr '\n' ' ')] [$(ls -A /home/gpitest/.cache 2> /dev/null | tr '\n' ' ')]"
    echo "ETC AFTER: [$(ls /etc/modprobe.d/pietato-loopback.conf /etc/modules-load.d/pietato-loopback.conf /etc/alsa/conf.d/60-pietato-web.conf /etc/pam.d/pietato-chromium 2> /dev/null | tr '\n' ' ')] [$(cd /etc/wireplumber 2> /dev/null && find . -type f | sort | tr '\n' ' ')]"
    echo "RCLOCAL AFTER: [$(tr '\n' '|' < /etc/rc.local 2> /dev/null)]"
    echo "CONFIG AFTER: [$(grep -c 'gpi-case setup' /boot/config.txt 2> /dev/null)]"
  done
fi
