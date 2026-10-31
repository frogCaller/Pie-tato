#!/usr/bin/env bash
# start.sh - Pietato on again after stop.sh: now, and every time the computer starts (on a PC with a desktop, in
# place of the desktop, as setup.sh set it up).
#
# Usage (from the Pietato folder):  sudo bash start.sh
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo bash start.sh"
  exit 1
fi

SYSD=/etc/systemd/system
WAS_DESKTOP=/var/lib/pitato/was-graphical      # (setup.sh: this computer started in its desktop before Pietato)

if [ ! -f "$SYSD/pitato.service" ] && [ ! -f "$SYSD/pitato-camera.service" ]; then
  echo "Pietato isn't set up on this computer: run  sudo bash setup.sh  first."
  exit 1
fi
for unit in pitato-web pitato-camera; do         # the web page, the camera server
  if [ -f "$SYSD/$unit.service" ]; then
    systemctl --quiet enable --now "$unit"
  fi
done
if [ ! -f "$SYSD/pitato.service" ]; then         # (a Pi that only shares its camera: setup.sh --camera)
  echo "The camera server's on again."
  exit 0
fi

systemctl --quiet enable pitato
if [ -f "$WAS_DESKTOP" ]; then
  systemctl set-default multi-user.target > /dev/null
fi
if systemctl is-active --quiet display-manager; then   # (never both at once: they'd fight over the screen)
  echo "Pietato's on: restart the computer and it starts in Pietato instead of the desktop."
else
  systemctl start pitato
  echo "Pietato's on, now and every time the computer starts."
fi
