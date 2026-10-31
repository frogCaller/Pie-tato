#!/usr/bin/env bash
# stop.sh - Pietato off: it stops now and doesn't start with the computer, so the computer starts as it did before
# (on a PC, its desktop) and Pietato takes none of its CPU. Everything stays as it is: start.sh turns it back on.
#
# Usage (from the Pietato folder):  sudo bash stop.sh
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo bash stop.sh"
  exit 1
fi

SYSD=/etc/systemd/system
WAS_DESKTOP=/var/lib/pitato/was-graphical      # (setup.sh: this computer started in its desktop before Pietato)

found=no
for unit in pitato pitato-web pitato-camera; do  # media mode, the web page, the camera server
  if [ -f "$SYSD/$unit.service" ]; then
    systemctl --quiet disable --now "$unit" || true
    found=yes
  fi
done
if [ "$found" = no ]; then
  echo "Pietato isn't set up on this computer."
  exit 0
fi
systemctl stop pietato-chromium 2> /dev/null || true    # (Chromium, if it was open)

echo "Pietato's off: it won't start with the computer. sudo bash start.sh turns it back on."
if grep -qs '^# >>> gpi-case setup >>>' /boot/firmware/config.txt /boot/config.txt; then
  echo "In the GPi Case, run  sudo poweroff  before you switch it off: the switch shuts down safely only with Pietato on."
fi
if [ -f "$WAS_DESKTOP" ]; then
  systemctl set-default graphical.target > /dev/null
  echo "The computer starts in its desktop again."
  if ! systemctl is-active --quiet display-manager; then
    systemctl --no-block start display-manager  # (last: run from the console, the desktop takes its place)
  fi
fi
