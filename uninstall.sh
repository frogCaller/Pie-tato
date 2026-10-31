#!/usr/bin/env bash
# uninstall.sh - Pietato taken off this computer: its services, its programs and the emulators it built, what it
# keeps for itself (its settings, sign-ins, the bot's voice), and what it changed (starting in place of the desktop
# on a PC, signing you in by itself, the web page's sound card, BlueALSA's settings).
#
# What's yours stays: your Videos, Music, Pictures, Documents and Games (with their saves), and this folder with
# your settings in it. So do the packages setup.sh put in (mplayer, ffmpeg, LibreOffice, Chromium, the emulators):
# other programs may use them. In a GPi Case, its screen and sound settings stay in config.txt, so the case keeps
# working.
#
# Usage (from the Pietato folder):  sudo bash uninstall.sh      (--yes: without asking first)
# (No set -e: if one thing can't go, the rest still does.)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo bash uninstall.sh"
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSD=/etc/systemd/system
if [ "$1" != --yes ]; then
  echo "This takes Pietato off this computer. Your own files, and this folder with your settings, stay."
  read -r -p "Take it off? [y/N] " ans || ans=""
  if [[ ! "$ans" =~ ^[Yy] ]]; then
    echo "Nothing changed."
    exit 0
  fi
fi

# who the web page ran as (its small copies of your pictures are in their home folder), and whether this computer
# started in its desktop before Pietato: looked at before they go
web_user="$(sed -n 's/^User=//p' "$SYSD/pitato-web.service" "$SYSD/pitato-camera.service" 2> /dev/null | head -n 1)"
web_user="${web_user:-${SUDO_USER:-}}"
user_home=""
if [ -n "$web_user" ]; then user_home="$(getent passwd "$web_user" | cut -d: -f6)"; fi
desktop=no
if [ -f /var/lib/pitato/was-graphical ]; then desktop=yes; fi

# its services: stopped, and gone
for unit in pitato pitato-web pitato-camera; do
  if [ -f "$SYSD/$unit.service" ]; then
    systemctl --quiet disable --now "$unit" || true
    rm -f "$SYSD/$unit.service"
  fi
done
systemctl stop pietato-chromium 2> /dev/null || true    # (Chromium, if it was open)

# signing you in by itself at start-up (setup.sh's): the console asks for the password again
login=no
if [ -f "$SYSD/getty@tty1.service.d/autologin.conf" ]; then
  rm -f "$SYSD/getty@tty1.service.d/autologin.conf"
  rmdir "$SYSD/getty@tty1.service.d" 2> /dev/null || true
  login=yes
fi
# BlueALSA as it comes, without setup.sh's settings for it
rm -f "$SYSD/bluealsa.service.d/pitato.conf"
rmdir "$SYSD/bluealsa.service.d" 2> /dev/null || true
systemctl daemon-reload
systemctl try-restart bluealsa 2> /dev/null || true
if [ "$desktop" = yes ]; then
  systemctl set-default graphical.target > /dev/null
fi

# the web page's sound card (Sound here and Mic here), and Chromium's session
rm -f /etc/modprobe.d/pietato-loopback.conf /etc/modules-load.d/pietato-loopback.conf \
  /etc/alsa/conf.d/60-pietato-web.conf /etc/wireplumber/main.lua.d/51-pietato-loopback.lua \
  /etc/wireplumber/wireplumber.conf.d/51-pietato-loopback.conf /etc/pam.d/pietato-chromium
rmdir /etc/wireplumber/main.lua.d /etc/wireplumber/wireplumber.conf.d 2> /dev/null || true
modprobe -r snd-aloop 2> /dev/null || true

# its programs, the emulators it built, and what it kept for itself
rm -f /usr/local/bin/pitato.py /var/log/pitato-update.log
rm -rf /usr/local/share/pitato /usr/local/lib/pitato /var/lib/pitato /var/cache/pitato
for core in pcsx_rearmed mupen64plus_next ppsspp melonds flycast; do
  rm -f "/usr/local/lib/libretro/${core}_libretro.so" "/usr/local/lib/libretro/$core.version"
done
rm -rf /usr/local/lib/libretro/PPSSPP
rmdir /usr/local/lib/libretro 2> /dev/null || true
if [ -n "$user_home" ] && [ "$user_home" != / ] && [ -d "$user_home/.cache/pitato" ]; then
  rm -rf "$user_home/.cache/pitato"
fi

# RetroFlag's own safe-shutdown script, if setup.sh turned it off for the GPi Case
retroflag=no
if [ -f /etc/rc.local ] && grep -qE '   # \(Pietato looks after the (case|power switch)\)$' /etc/rc.local; then
  sed -i -E 's@^# (.*)   # \(Pietato looks after the (case|power switch)\)$@\1@' /etc/rc.local
  retroflag=yes
fi

echo
echo "Pietato is removed from this computer."
echo "Your Videos, Music, Pictures, Documents and Games are still here, and so is $HERE"
echo "with your settings in it: delete it too if you don't need them."
echo "The packages setup.sh put in (LibreOffice, Chromium, mplayer, the emulators) stay: other programs may use them."
if [ "$login" = yes ]; then echo "The console asks for your password at start-up again."; fi
if [ "$retroflag" = yes ]; then echo "RetroFlag's safe-shutdown script is back on in /etc/rc.local."; fi
if grep -qs '^# >>> gpi-case setup >>>' /boot/firmware/config.txt /boot/config.txt; then
  echo "The GPi Case's screen and sound settings stay in config.txt, so the case keeps working."
fi
if [ "$desktop" = yes ]; then
  echo "The computer starts in its desktop again."
  if ! systemctl is-active --quiet display-manager; then
    systemctl --no-block start display-manager  # (last: run from the console, the desktop takes its place)
  fi
fi
