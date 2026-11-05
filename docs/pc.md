# On a PC

If you have a regular computer (Intel or AMD) with Ubuntu 24.04 (Desktop or Server) or Debian 12 or 13, you can
run it there too and play with a USB or Bluetooth controller. Set it up the same way, with the commands in the
[README](../README.md#install) (if git isn't there yet, `sudo apt install git` first).
On Debian, setup.sh also turns on Debian's non-free packages, where the SNES and Genesis emulators are. If
sudo isn't there (you gave root a password when you installed Debian), use `su -c` instead:
`su -c "apt install git"`, then `su -c "bash setup.sh"` in the Pietato folder, and the same for the other
scripts ([Setting it up](setup.md) has them).
It builds every game emulator (about an hour, or fewer in Custom), so leave the computer on until it says All set.
After that, the computer starts in Pietato, like a console. If you have a desktop, open System,
press SELECT for its list and pick Desktop to use it, then restart the computer to come back to Pietato.
Settings > Resolution sets the screen's size at start-up. With a desktop installed, Bluetooth
headphones only play sound on the desktop, so in Pietato use the computer's speakers, HDMI or a USB speaker.
