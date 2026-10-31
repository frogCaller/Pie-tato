#!/usr/bin/env bash
# setup.sh - set up Raspberry Pi OS Lite (Bookworm) on any Raspberry Pi with a screen, or Ubuntu 24.04 on a PC
#   - in a RetroFlag GPi Case 2W (Pi Zero 2 W): the case screen as the console (with
#     GPIO 18/19 left free for the speaker), the case speaker, and its power switch:
#     switching off shuts the Pi down safely (GPIO 26 and 27, as RetroFlag's own script)
#   - in a RetroFlag GPi Case 2 (Compute Module 4): the case screen, or in its dock the TV
#     (picked as the Pi starts, GPIO 18 saying which; Pietato restarts the Pi when it's
#     docked or taken out), the case's sound, and its power switch, as the 2W's
#   - on any other Pi: the screen on HDMI as it is
#   - on a PC (Intel or AMD, Ubuntu): every emulator built for it, and it starts in Pietato; with Ubuntu's desktop,
#     the terminal instead of the desktop at start-up (System > Desktop starts the desktop till it restarts)
#   - game controller buttons as keys + media mode (the case buttons, or any USB or
#     Bluetooth controller), which opens at start-up on a home screen of app icons: TV (Plex,
#     cartoons, free movies, news, sports, streams, a TV remote through Home Assistant),
#     music, radio, photos (filters, delete), videos, weather, stock and coin prices and charts,
#     the web (a browser of its own, and Chromium on a Pi 4 or 5),
#     a file browser for PDFs/documents/text, cameras on your other Pis (see
#     --camera below) with OBSBOT steering and pictures, a bot (Ollama on another
#     computer, a Piper voice on the Pi; at work it acts out your coding agent and sends
#     it your prompts), a Simulator (rock paper scissors, the game of life, forest fire, the
#     Mandelbrot set to tour or explore, cmatrix, hollywood, nyancat, cacafire, htop), Snake
#     and your own Game Boy, Game Boy Advance, NES, SNES, Genesis, Master System, Game Gear,
#     PlayStation and (on a Pi 4 or
#     5) N64, PSP, DS and Dreamcast games, two players on two controllers (mGBA, Nestopia, Snes9x,
#     Genesis Plus GX, and PCSX ReARMed, Mupen64Plus-Next, PPSSPP, melonDS and Flycast built here),
#     system info, and settings (WiFi, Bluetooth and its headphones, background, colours,
#     location, sound, controller, bot...)  (pitato.py and the Pietato folder, run at boot)
#   - a web page for your phone or computer (webui.py, port 5432): see the screen, work
#     it with a remote, put cartoons, films, news or radio on it, and drag in files
#     that land in Music, Videos, Pictures or Documents
#   - the console signs you in by itself at start-up, so it's ready after a reboot
#   - Bluetooth on: pair controllers, keyboards, headphones and the rest in Settings >
#     Bluetooth, or on the web page; sound plays through headphones and speakers (BlueALSA)
#
# Your settings files (radio.txt, bot.txt, finance.txt...) go in this folder's static folder, so
# keep the folder where it is. Ones left in your home folder by an earlier version move there.
#
# Usage (from the repo folder):  sudo bash setup.sh
#   --gpi       it's in a GPi Case (don't ask): the 2W on a Pi Zero, the GPi Case 2 on a CM4
#   --gpi2      it's in a GPi Case 2 (don't ask)
#   --no-gpi    it isn't (don't ask)
#   --login     keep asking for your password at start-up (instead of signing you in by itself)
#   --camera    only share this Pi's USB camera on the network, for Pietato's Camera tab on
#               another Pi (camera.py, port 5433); nothing else is installed
#   --update    no questions: it's set up as it was before (System > Update software runs it
#               after git pull, then restarts the Pi itself)
#   --image     for an SD card image (image/build.sh): no questions, every emulator built (for any
#               Pi), nothing started and no restart; with --gpi for the GPi Case 2W, --gpi2
#               for the GPi Case 2
# Safe to run again: it replaces its own settings instead of adding duplicates.

set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo bash setup.sh"
  exit 1
fi

GPI=""          # yes: it's in a GPi Case (CASE says which); no: it isn't; "": ask
CASE=""         # 2w: the GPi Case 2W (a Pi Zero 2 W); 2: the GPi Case 2 (a Compute Module 4)
CAMERA=no
LOGIN=no
UPDATE=no
IMAGE=no
for arg in "$@"; do
  case "$arg" in
    --gpi) GPI=yes ;;
    --gpi2) GPI=yes CASE=2 ;;
    --no-gpi) GPI=no ;;
    --login) LOGIN=yes ;;
    --camera) CAMERA=yes ;;
    --update) UPDATE=yes ;;
    --image) IMAGE=yes ;;
    *) echo "Unknown option: $arg (use --gpi, --gpi2, --no-gpi, --login, --camera, --update or --image)"; exit 1 ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
STATIC="$HERE/static"                  # your settings files
case "$HERE" in
  *[\"\\]*) echo "Move the Pietato folder somewhere without quotes or backslashes in its path."; exit 1 ;;
esac
if [ "$HERE" = "$USER_HOME" ] || [ "$HERE" = / ]; then
  echo "Keep Pietato in a folder of its own (git clone makes one), not in $HERE itself."
  exit 1
fi
UNIT_STATIC="${STATIC//%/%%}"          # (as a systemd unit writes it)
if id "$USER_NAME" >/dev/null 2>&1 && command -v runuser >/dev/null \
   && ! runuser -u "$USER_NAME" -- test -r "$HERE" -a -x "$HERE"; then
  echo "$USER_NAME can't open $HERE, so the web page couldn't reach your settings in it."
  echo "Clone Pietato into $USER_HOME and run setup.sh from there."
  exit 1
fi

step() { echo; echo "==> $*"; }

# A long quiet job (a download, a build): its output into a log, and meanwhile a line that keeps moving, with how
# long it's taken so far (and how far it's got, for a build that says), so it's clear the Pi is still working.
# When the output goes to a file rather than a screen: a line a minute
SPIN=""
SPIN_ON=""         # (a file that's there while the moving line should be)
working() {        # working WHAT LOG COMMAND...: COMMAND's exit status
  local what="$1" log="$2" rc=0 t0=$SECONDS
  shift 2
  SPIN_ON="$log.spinning"; : > "$SPIN_ON"
  trap - EXIT; spin "$what" "$log" "$SPIN_ON" & SPIN=$!; trap on_exit EXIT   # (it mustn't run setup.sh's tidy-up)
  ( "$@" ) < /dev/null >> "$log" 2>&1 || rc=$?       # (in a subshell: if it's stopped, setup.sh still says so)
  stop_spin
  if [ "$rc" -eq 0 ]; then echo "  $what: done (took $(elapsed $((SECONDS - t0))))"; fi
  return "$rc"
}
spin() {           # (working's moving line, while its file is there)
  set +e
  local what="$1" log="$2" on="$3" t0=$SECONDS t i=0 next=60 p pct="" cols line marks='|/-\'
  if [ -t 1 ]; then trap 'printf "\r\033[K"; exit 0' TERM; else trap 'exit 0' TERM; fi
  trap '' INT                                               # (Ctrl+C: setup.sh stops this itself, line wiped)
  exec 3>&1
  while [ -e "$on" ] && kill -0 "$$" 2> /dev/null; do       # (setup.sh: if it's gone, this goes too)
    t=$((SECONDS - t0))
    if [ -t 1 ]; then
      p=$(tail -c 3000 "$log" 2> /dev/null | grep -o '^\[ *[0-9]*%\]' | tail -n 1 | tr -dc 0-9)
      if [ -n "$p" ]; then pct=" $p%"; fi
      cols=$(stty size <&3 2> /dev/null); cols=${cols#* }
      [ "${cols:-0}" -gt 20 ] 2> /dev/null || cols=80
      line="  ${marks:i++%4:1} $what$pct  $(elapsed "$t")  Still working: leave the $MACHINE on"
      printf '\r%s\033[K' "${line:0:cols-1}"                # (one line, however narrow the screen)
    elif [ "$t" -ge "$next" ]; then
      echo "  $what: still working ($((t / 60)) min so far)"
      next=$((next + 60))
    fi
    sleep 1 & wait $!
  done
  if [ -t 1 ]; then printf '\r\033[K'; fi
}
stop_spin() {
  if [ -n "$SPIN" ]; then
    rm -f "$SPIN_ON"                        # (it stops at its next look, even if what's next goes astray,
    kill "$SPIN" 2> /dev/null || true       #  as it can when it's only just started; this stops it at once)
    wait "$SPIN" 2> /dev/null || true
    SPIN=""
  fi
}
elapsed() {        # elapsed SECONDS: 4:05, or 1:02:05
  if [ "$1" -ge 3600 ]; then printf '%d:%02d:%02d' $(($1 / 3600)) $(($1 % 3600 / 60)) $(($1 % 60))
  else printf '%d:%02d' $(($1 / 60)) $(($1 % 60)); fi
}
how_long() {       # how_long PI PC: how long it takes, on a Pi or on a PC
  if [ "$PC" = yes ]; then echo "$2"; else echo "$1"; fi
}
fetch_source() {   # fetch_source URL FOLDER: a .tar.gz, unpacked into FOLDER
  curl -fsSL "$1" | tar -xz -C "$2" --strip-components=1
}

# your settings files: into the static folder (an earlier version kept them in your home folder)
settings_folder() {
  mkdir -p "$STATIC"
  chown "$USER_NAME:$USER_NAME" "$STATIC" || true
  local f
  for f in "$@"; do
    [ -f "$USER_HOME/$f" ] && [ ! -L "$USER_HOME/$f" ] || continue
    if [ -e "$STATIC/$f" ]; then
      echo "Keeping $STATIC/$f (there's an older $f in $USER_HOME you can delete)"
    else
      mv "$USER_HOME/$f" "$STATIC/$f" && echo "Moved $f from $USER_HOME into $STATIC" || true
    fi
  done
  return 0
}

# --------------------------------------------------------------------------
# the camera server (camera.py, port 5433): this Pi's USB camera, for Pietato's Camera tab on another Pi
install_camera() {
  step "Installing the camera server (this Pi's USB camera, port 5433)"
  apt-get update
  apt-get install -y ffmpeg v4l-utils python3
  install -d /usr/local/share/pitato
  install -m 644 "$HERE/pitato/camera.py" /usr/local/share/pitato/camera.py
  settings_folder camera-server.txt
  usermod -aG video "$USER_NAME" || true
  if [ -f /etc/systemd/system/gpi-camera.service ]; then     # (by the name it had before Pietato's)
    systemctl disable --now gpi-camera 2>/dev/null || true
    rm -f /etc/systemd/system/gpi-camera.service /usr/local/share/gpi-media/camera.py
    rmdir /usr/local/share/gpi-media 2>/dev/null || true
  fi
  cat > /etc/systemd/system/pitato-camera.service <<CAMSVC
[Unit]
Description=Pietato camera server: this Pi's USB camera on the network (port 5433)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
SupplementaryGroups=video
WorkingDirectory=$USER_HOME
Environment="PITATO_STATIC=$UNIT_STATIC"
ExecStart=/usr/bin/python3 /usr/local/share/pitato/camera.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
CAMSVC
  systemctl daemon-reload
  systemctl enable pitato-camera
  systemctl restart pitato-camera || true
}

# --camera: this Pi only shares its USB camera
if [ "$CAMERA" = yes ]; then
  if [ ! -f "$HERE/pitato/camera.py" ]; then
    echo "pitato/camera.py isn't here. Run this from the Pietato folder."
    exit 1
  fi
  install_camera
  echo
  echo "Done. On Pietato's Camera tab, add this Pi:  $(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "It also shows up there by itself, under On your network."
  echo "To see the picture in a browser:  http://$(hostname).local:5433"
  exit 0
fi

for f in pitato.py pitato/app.py pitato/webui.py pitato/coder_hooks.py templates/index.html; do
  if [ ! -f "$HERE/$f" ]; then
    echo "$f isn't here. Run this from the Pietato folder."
    exit 1
  fi
done

if [ -d /boot/firmware ]; then BOOT=/boot/firmware; else BOOT=/boot; fi
CONFIG="$BOOT/config.txt"
MODEL="$(tr -d '\0' 2> /dev/null < "${PITATO_MODEL_FILE:-/proc/device-tree/model}" || true)"   # (none where an
                                                                                                # image is made)
# a computer of your own (Intel or AMD, with Ubuntu) rather than a Pi: no config.txt, no GPi Case, and every emulator
PC=no
if [[ "$MODEL" != *"Raspberry Pi"* ]] && [ ! -f "$CONFIG" ] && [ "$IMAGE" != yes ]; then
  case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
    amd64|x86_64) PC=yes ;;
  esac
fi
if [ "$PC" = yes ]; then MACHINE=computer; else MACHINE=Pi; fi     # (what to leave on while it works)

# Until it's done, a shutdown asked for gently (a Pi 5's power button, the GPi Case's switch, poweroff without
# sudo) waits. Nothing can stop a pulled plug, so it says to leave the Pi on. If it stops early (an error, Ctrl+C),
# it says so, and clears away the emulator it was partway through building
FINISHED=no
BUILDING=""        # (that emulator's folder in /var/tmp)
HOLD=""
if command -v systemd-inhibit > /dev/null 2>&1; then
  systemd-inhibit --what=shutdown:sleep:handle-power-key --mode=block --who="Pietato setup" \
    --why="Setting up Pietato: leave the $MACHINE on until it says All set" \
    bash -c 'while kill -0 "$1" 2> /dev/null; do sleep 2; done' _ "$$" > /dev/null 2>&1 &   # (ends with setup.sh)
  HOLD=$!
fi
let_go() {
  if [ -n "$HOLD" ]; then
    kill "$HOLD" 2> /dev/null || true
    wait "$HOLD" 2> /dev/null || true
    HOLD=""
  fi
}
on_exit() {
  [ "$BASHPID" = "$$" ] || return 0
  set +e
  stop_spin
  let_go
  if [ -n "$BUILDING" ]; then rm -rf "$BUILDING"; fi
  if [ "$FINISHED" != yes ]; then
    echo
    echo "setup.sh stopped before it was done. Run  sudo bash setup.sh  again to finish."
  fi
}
trap on_exit EXIT
trap 'exit 130' INT      # (Ctrl+C stops it, even when what was running when you pressed it took it in its stride)


# --------------------------------------------------------------------------
# a GPi Case needs its own screen and sound settings (the 2W's, or the GPi Case 2's); any other Pi uses HDMI
CM4=no          # a Compute Module 4 (not a 4S): what the GPi Case 2 takes
case "$MODEL" in
  *"Compute Module 4 "*|*"Compute Module 4") CM4=yes ;;
esac
WAS=""          # the case it was set up for before (setup.sh's part of config.txt says): 2w, 2, or none
if grep -q '^# >>> gpi-case setup >>>' "$CONFIG" 2>/dev/null; then
  if sed -n '/^# >>> gpi-case setup >>>/,/^# <<< gpi-case setup <<</p' "$CONFIG" | grep -q '^# GPi Case 2 (CM4)'; then
    WAS=2
  else
    WAS=2w
  fi
fi
BIG=no          # a Pi 4 or 5: N64, PSP, DS and Dreamcast games too (their emulators built here), and Chromium
case "$MODEL" in
  *"Pi 4"*|*"Pi 5"*|*"Compute Module 4"*|*"Compute Module 5"*) BIG=yes ;;
esac
if [ "$IMAGE" = yes ]; then  # (an image, for any Pi: made on another computer, whose own model doesn't count)
  BIG=yes
  if [ -z "$GPI" ]; then GPI=no; fi
fi
if [ "$PC" = yes ]; then     # (a PC: every emulator, and Chromium; never in a GPi Case)
  BIG=yes GPI=no CASE=""
fi
if [ -z "$GPI" ] && [ "$UPDATE" = yes ]; then       # (as it was set up: the case's settings there, or not)
  if [ -n "$WAS" ]; then GPI=yes CASE="${CASE:-$WAS}"; else GPI=no; fi
fi
if [ -z "$GPI" ]; then
  if [ "$WAS" = 2 ]; then                          # (set up for it before: yes, unless you say otherwise)
    read -r -p "Is this Pi in a RetroFlag GPi Case 2? [Y/n] " ans
    if [[ "$ans" =~ ^[Nn] ]]; then GPI=no; else GPI=yes CASE=2; fi
  elif [ "$CM4" = yes ]; then                      # (a CM4 is often on a board of its own, on HDMI: no, unless you say)
    read -r -p "Is this Pi in a RetroFlag GPi Case 2? [y/N] " ans
    if [[ "$ans" =~ ^[Yy] ]]; then GPI=yes CASE=2; else GPI=no; fi
  elif [[ "$MODEL" == *Zero* ]] || [ "$WAS" = 2w ]; then
    read -r -p "Is this Pi in a RetroFlag GPi Case 2W? [Y/n] " ans
    if [[ "$ans" =~ ^[Nn] ]]; then GPI=no; else GPI=yes CASE=2w; fi
  else
    GPI=no      # the cases take a Pi Zero (the 2W) or a Compute Module 4 (the GPi Case 2)
  fi
fi
if [ "$GPI" = yes ] && [ -z "$CASE" ]; then         # (--gpi: the case this Pi goes in; an image's, the 2W)
  if [ "$CM4" = yes ] && [ "$IMAGE" != yes ]; then CASE=2; else CASE=2w; fi
fi
if [ "$GPI" = yes ] && [ "$CASE" = 2 ]; then
  echo "Setting up for the GPi Case 2: its screen (or a TV, in its dock), sound and buttons."
elif [ "$GPI" = yes ]; then
  echo "Setting up for the GPi Case 2W: its screen, speaker and buttons."
elif [ "$PC" = yes ]; then
  echo "Setting up this computer. Plug in any USB or Bluetooth game controller."
else
  echo "Setting up for a screen on HDMI${MODEL:+ ($MODEL)}. Plug in any USB or Bluetooth game controller."
fi
if [ "$PC" = yes ]; then
  echo "The first time takes a while (about half an hour) as it builds the game emulators."
else
  echo "The first time takes a while: an hour or more on a Pi 4, as it builds the game emulators."
fi
echo "Leave the $MACHINE on until it says All set."

# --------------------------------------------------------------------------
step "Installing packages"
apt-get update
apt-get install -y python3-evdev python3-pil python3-numpy fonts-dejavu-core \
  mplayer poppler-utils iw evtest device-tree-compiler python3-flask alsa-utils ffmpeg bluez
# a USB camera (v4l2-ctl: its sizes, and turning one that turns) and a USB microphone (Vosk needs libatomic)
apt-get install -y v4l-utils libatomic1 || echo "(Couldn't install v4l-utils or libatomic1: a USB camera or microphone may not work.)"
# the Simulator's cmatrix, nyancat, htop and hollywood: Linux's own. hollywood with what its panes show, but not
# atop or plocate, which would keep running in the background
apt-get install -y cmatrix || echo "(Couldn't install cmatrix: the Simulator's cmatrix won't start.)"
apt-get install -y nyancat || echo "(Couldn't install nyancat: the Simulator's nyancat won't start.)"
apt-get install -y htop || echo "(Couldn't install htop: the Simulator's htop won't start.)"
apt-get install -y --no-install-recommends hollywood \
  || echo "(Couldn't install hollywood: the Simulator's hollywood won't start.)"
apt-get install -y --no-install-recommends apg bmon bsdextrautils ccze htop jp2a moreutils speedometer tree \
  || echo "(Couldn't install some of what hollywood's panes show: it shows the rest.)"
# and cacafire: libcaca's own, built here from its one source file, without its "Powered by libcaca"
CACAFIRE=373c88b9890e67bde91e6acb8f1c442e847d1203        # (libcaca 0.99.beta20: Raspberry Pi OS's own libcaca)
PROGS=/usr/local/lib/pitato
build_cacafire() {
  local tmp
  apt-get install -y build-essential curl libcaca-dev || return 1
  tmp="$(mktemp -d /var/tmp/cacafire-XXXXXX)" || return 1
  BUILDING="$tmp"
  curl -fsSL "https://raw.githubusercontent.com/cacalabs/libcaca/$CACAFIRE/src/aafire.c" -o "$tmp/aafire.c" \
    && sed -i 's/ -=\[ Powered by libcaca \]=- //' "$tmp/aafire.c" && ! grep -q 'Powered by libcaca' "$tmp/aafire.c" \
    && : > "$tmp/config.h" \
    && gcc -O2 -DLIBCACA -I"$tmp" -o "$tmp/cacafire" "$tmp/aafire.c" -lcaca -lm > "$tmp/build.log" 2>&1 \
    || { tail -n 20 "$tmp/build.log" 2> /dev/null; rm -rf "$tmp"; return 1; }
  install -d "$PROGS" && install -m 755 "$tmp/cacafire" "$PROGS/cacafire" || { rm -rf "$tmp"; return 1; }
  echo "$CACAFIRE" > "$PROGS/cacafire.version"
  rm -rf "$tmp"
}
if [ "$(cat "$PROGS/cacafire.version" 2>/dev/null)" = "$CACAFIRE" ] && [ -x "$PROGS/cacafire" ]; then
  echo "The Simulator's cacafire is built already."
else
  build_cacafire || echo "(Couldn't build cacafire: the Simulator's cacafire won't start.)"
fi
# Files > Other computers: Windows and Mac shared folders (cifs-utils, smbclient, and nmblookup in samba-common-bin
# for a PC's own name), Linux computers over SSH (sshfs). (Without questions: samba-common asks one about WINS, and
# the answer it'd take is No.)
DEBIAN_FRONTEND=noninteractive apt-get install -y cifs-utils smbclient samba-common-bin sshfs \
  || echo "(Couldn't install what opens other computers' files: Files > Other computers won't open them.)"
# the Games tab's emulators: Game Boy, Color and Advance (mGBA), NES (Nestopia), SNES (Snes9x), and Genesis (Mega
# Drive), Master System and Game Gear (Genesis Plus GX)
for pkg in libretro-mgba libretro-nestopia libretro-snes9x libretro-genesisplusgx; do
  apt-get install -y "$pkg" || echo "(Couldn't install $pkg: the games it plays won't start without it.)"
done

# PlayStation: PCSX ReARMed, built here from its source (Debian doesn't have it), tuned for this Pi
PCSX_REARMED=c8816799b50388e61cfe237fe2cdbb7d8175f20a
CORES=/usr/local/lib/libretro
build_pcsx_rearmed() {
  local plat jobs tmp
  # (the system's own kind, not the kernel's: a 32-bit Raspberry Pi OS can run a 64-bit kernel)
  case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
    arm64|aarch64)
      case "$MODEL" in
        *"Pi 4"*|*"Pi 5"*|*"Compute Module 4"*|*"Compute Module 5"*) plat=rpi4_64 ;;   # (400 and 500 too)
        *"Pi 3"*|*"Zero 2"*|*"Compute Module 3"*) plat=rpi3_64 ;;
        *) plat=unix ;;
      esac
      if [ "$IMAGE" = yes ]; then plat=rpi3_64; fi ;;     # (an image: the slowest 64-bit Pi's, which all run)
    armhf|armv7l|armv6l)
      case "$MODEL" in
        *"Pi 4"*|*"Pi 5"*|*"Compute Module 4"*) plat=rpi4 ;;
        *"Pi 3"*|*"Zero 2"*|*"Compute Module 3"*) plat=rpi3 ;;
        *"Pi 2"*) plat=rpi2 ;;
        *Zero*|"Raspberry Pi Model"*|*"Compute Module Rev"*) plat=rpi1 ;;   # (the first Pis, and the Zero W)
        *) plat=unix ;;
      esac ;;
    *) plat=unix ;;
  esac
  jobs=$(nproc 2>/dev/null || echo 1)
  if [ "$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)" -lt 1000 ]; then jobs=1; fi   # (a Pi Zero's 512 MB)
  apt-get install -y build-essential curl || return 1
  tmp="$(mktemp -d /var/tmp/pcsx_rearmed-XXXXXX)" || return 1      # (not /tmp: on some systems that's in memory)
  BUILDING="$tmp"
  working "Downloading" "$tmp/build.log" \
      fetch_source "https://github.com/libretro/pcsx_rearmed/archive/$PCSX_REARMED.tar.gz" "$tmp" \
    && working "Building" "$tmp/build.log" make -C "$tmp" -f Makefile.libretro platform="$plat" -j"$jobs" \
    || { tail -n 20 "$tmp/build.log"; rm -rf "$tmp"; return 1; }
  install -d "$CORES" && install -m 644 "$tmp/pcsx_rearmed_libretro.so" "$CORES/" || { rm -rf "$tmp"; return 1; }
  echo "$PCSX_REARMED" > "$CORES/pcsx_rearmed.version"
  rm -rf "$tmp"
}
if [ "$(cat "$CORES/pcsx_rearmed.version" 2>/dev/null)" = "$PCSX_REARMED" ] && [ -f "$CORES/pcsx_rearmed_libretro.so" ]; then
  echo "The PlayStation emulator (PCSX ReARMed) is built already."
else
  step "Building the PlayStation emulator (PCSX ReARMed): $(how_long "a few minutes, longer on a Pi Zero" "a few minutes")"
  if ! build_pcsx_rearmed; then
    echo "(Couldn't build PCSX ReARMed. Trying Debian's Beetle PSX instead: it needs scph5501.bin in"
    echo " ~/Games/BIOS, and it's too slow for a Pi Zero.)"
    apt-get install -y libretro-beetle-psx || echo "(No PlayStation emulator: PlayStation games won't start.)"
  fi
fi

# N64: Mupen64Plus-Next, built here from its source, on a Pi 4 or 5 only: it draws in 3D with their graphics
# chip (OpenGL ES 3), which older Pis don't have
MUPEN64PLUS=12edd2c74a517ff86dfa8cfc71ad75e4c10486d5
build_mupen64plus() {
  local plat arch jobs tmp mem gles=""
  # (the system's own kind, not the kernel's: a 32-bit Raspberry Pi OS can run a 64-bit kernel). A Pi 5
  # runs the Pi 4's build: the same OpenGL ES 3 drawing, without the extras it'd add. A PC: its own build,
  # drawing with OpenGL ES 3 too (media mode's way of drawing a 3D game: pitato/gpu.py)
  case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
    arm64|aarch64) arch=aarch64; plat=rpi4_64 ;;
    armhf|armv7l) arch=arm; plat=rpi4 ;;
    amd64|x86_64) arch=x86_64; plat=unix; gles="FORCE_GLES3=1" ;;
    *) return 1 ;;
  esac
  jobs=$(nproc 2>/dev/null || echo 1)
  mem=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
  if [ "$mem" -lt 1000 ]; then jobs=1; elif [ "$mem" -lt 2000 ] && [ "$jobs" -gt 2 ]; then jobs=2; fi
  apt-get install -y build-essential curl libgles-dev libegl-dev \
    libegl-mesa0 libgl1-mesa-dri libgbm1 || return 1                      # (Mesa too, to run it)
  tmp="$(mktemp -d /var/tmp/mupen64plus-XXXXXX)" || return 1
  BUILDING="$tmp"
  working "Downloading" "$tmp/build.log" \
      fetch_source "https://github.com/libretro/mupen64plus-libretro-nx/archive/$MUPEN64PLUS.tar.gz" "$tmp" \
    && working "Building" "$tmp/build.log" make -C "$tmp" platform="$plat" ARCH="$arch" $gles -j"$jobs" \
    || { tail -n 20 "$tmp/build.log"; rm -rf "$tmp"; return 1; }
  install -d "$CORES" && install -m 644 "$tmp/mupen64plus_next_libretro.so" "$CORES/" || { rm -rf "$tmp"; return 1; }
  echo "$MUPEN64PLUS" > "$CORES/mupen64plus_next.version"
  rm -rf "$tmp"
}
if [ "$BIG" = yes ]; then
  if [ "$(cat "$CORES/mupen64plus_next.version" 2>/dev/null)" = "$MUPEN64PLUS" ] \
      && [ -f "$CORES/mupen64plus_next_libretro.so" ]; then
    echo "The N64 emulator (Mupen64Plus-Next) is built already."
  else
    step "Building the N64 emulator (Mupen64Plus-Next): $(how_long "about 20 minutes on a Pi 4, less on a Pi 5" "a few minutes")"
    build_mupen64plus || echo "(Couldn't build Mupen64Plus-Next: N64 games won't start.)"
  fi
else
  echo "(N64 games need a Pi 4 or 5: no N64 emulator on this one.)"
fi

# PSP: PPSSPP, built here from its source, on a Pi 4 or 5 only (it draws in 3D with their graphics chip too),
# with patches/ppsspp-libretro-threads.patch (pausing, starting over and quitting made safe). Its own files (the
# PSP's fonts and so on) go beside it, in $CORES/PPSSPP
PPSSPP=v1.20.4
PPSSPP_BUILT="$PPSSPP+threads"    # (what's noted once it's built: a new patch builds it again)
ppsspp_source() {  # ppsspp_source FOLDER ARCH
  local tmp="$1" arch="$2" sha
  local -x GIT_TERMINAL_PROMPT=0     # (a question from git would wait unseen: an error instead)
  # its source, and the parts it's built from (not its tests, nor what other systems need)
  git -c advice.detachedHead=false clone -q --depth 1 --branch "$PPSSPP" https://github.com/hrydgard/ppsspp.git "$tmp/src" \
    && git -C "$tmp/src" submodule update -q --init --depth 1 --recursive -- libretro/libretro-common \
         ext/armips ext/glslang ext/SPIRV-Cross ext/rapidjson ext/zstd ext/cpu_features ext/rcheevos ext/naett \
         ext/libchdr ext/OpenXR-SDK ext/lua ext/nanosvg ext/aemu_postoffice ext/miniupnp \
    && git -C "$tmp/src" apply "$HERE/patches/ppsspp-libretro-threads.patch" \
    && sha=$(git -C "$tmp/src" ls-tree HEAD ffmpeg | awk '{print $3}') \
    || return 1
  # FFmpeg (for a game's films), ready-built for this kind of Pi: only that part of it
  git clone -q --filter=blob:none --no-checkout --depth 1 https://github.com/hrydgard/ppsspp-ffmpeg.git "$tmp/src/ffmpeg" \
    && git -C "$tmp/src/ffmpeg" sparse-checkout set --no-cone "/linux/$arch/" \
    && git -C "$tmp/src/ffmpeg" fetch -q --depth 1 origin "$sha" \
    && git -C "$tmp/src/ffmpeg" checkout -q "$sha"
}
ppsspp_make() {    # ppsspp_make FOLDER JOBS (OpenGL ES, drawn in for media mode: no X11 or Wayland)
  cmake -S "$1/src" -B "$1/build" -DCMAKE_BUILD_TYPE=Release -DLIBRETRO=ON -DUSING_GLES2=ON \
      -DUSING_X11_VULKAN=OFF -DUSE_WAYLAND_WSI=OFF -DUSE_DISCORD=OFF -DUSE_MINIUPNPC=OFF \
      -DCMAKE_DISABLE_FIND_PACKAGE_X11=ON -DCMAKE_DISABLE_FIND_PACKAGE_Wayland=ON \
    && make -C "$1/build" -j"$2" ppsspp_libretro
}
build_ppsspp() {
  local arch jobs mem tmp so
  case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
    arm64|aarch64) arch=aarch64 ;;
    armhf|armv7l) arch=armv7 ;;
    amd64|x86_64) arch=x86_64 ;;
    *) return 1 ;;
  esac
  jobs=$(nproc 2>/dev/null || echo 1)
  mem=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
  if [ "$mem" -lt 1500 ]; then jobs=1; elif [ "$mem" -lt 3000 ] && [ "$jobs" -gt 2 ]; then jobs=2; fi
  apt-get install -y build-essential git cmake libgles-dev libegl-dev \
    libegl-mesa0 libgl1-mesa-dri libgbm1 || return 1                      # (Mesa too, to run it)
  tmp="$(mktemp -d /var/tmp/ppsspp-XXXXXX)" || return 1
  BUILDING="$tmp"
  working "Downloading" "$tmp/build.log" ppsspp_source "$tmp" "$arch" \
    && working "Building" "$tmp/build.log" ppsspp_make "$tmp" "$jobs" \
    || { tail -n 20 "$tmp/build.log"; rm -rf "$tmp"; return 1; }
  so="$(find "$tmp/build" -name ppsspp_libretro.so | head -n 1)"
  install -d "$CORES" && install -m 644 "$so" "$CORES/" \
    && rm -rf "$CORES/PPSSPP" && cp -r "$tmp/src/assets" "$CORES/PPSSPP" || { rm -rf "$tmp"; return 1; }
  echo "$PPSSPP_BUILT" > "$CORES/ppsspp.version"
  rm -rf "$tmp"
}
if [ "$BIG" = yes ]; then
  if [ "$(cat "$CORES/ppsspp.version" 2>/dev/null)" = "$PPSSPP_BUILT" ] && [ -f "$CORES/ppsspp_libretro.so" ] \
      && [ -f "$CORES/PPSSPP/compat.ini" ]; then
    echo "The PSP emulator (PPSSPP) is built already."
  else
    step "Building the PSP emulator (PPSSPP): $(how_long "about an hour on a Pi 4, 20 minutes on a Pi 5" "about 15 minutes")"
    build_ppsspp || echo "(Couldn't build PPSSPP: PSP games won't start.)"
  fi
else
  echo "(PSP games need a Pi 4 or 5: no PSP emulator on this one.)"
fi

# DS: melonDS, built here from its source, on a Pi 4 or 5 with the 64-bit Raspberry Pi OS: its quick way of running
# a DS's two processors (a JIT) is 64-bit ARM's, and without it the games play too slowly. It draws them itself, in
# the Pi's processor; Pi 4's build, on a Pi 5 too
MELONDS=66b5d2634cd0a79030562811e6e05f5532f800ba
melonds_source() {  # melonds_source FOLDER
  local -x GIT_TERMINAL_PROMPT=0     # (a question from git would wait unseen: an error instead)
  git init -q "$1/src" \
    && git -C "$1/src" fetch -q --depth 1 https://github.com/libretro/melonDS.git "$MELONDS" \
    && git -C "$1/src" -c advice.detachedHead=false checkout -q FETCH_HEAD
}
build_melonds() {
  local jobs mem tmp plat=rpi4_64
  if [ "$PC" = yes ]; then plat=unix; fi            # (a PC's: melonDS's JIT for Intel and AMD)
  jobs=$(nproc 2>/dev/null || echo 1)
  mem=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
  if [ "$mem" -lt 1500 ]; then jobs=1; elif [ "$mem" -lt 3000 ] && [ "$jobs" -gt 2 ]; then jobs=2; fi
  apt-get install -y build-essential git libgles-dev || return 1
  tmp="$(mktemp -d /var/tmp/melonds-XXXXXX)" || return 1
  BUILDING="$tmp"
  working "Downloading" "$tmp/build.log" melonds_source "$tmp" \
    && working "Building" "$tmp/build.log" make -C "$tmp/src" platform="$plat" -j"$jobs" \
    || { tail -n 20 "$tmp/build.log"; rm -rf "$tmp"; return 1; }
  install -d "$CORES" && install -m 644 "$tmp/src/melonds_libretro.so" "$CORES/" || { rm -rf "$tmp"; return 1; }
  echo "$MELONDS" > "$CORES/melonds.version"
  rm -rf "$tmp"
}
if [ "$BIG" = yes ]; then
  case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
    arm64|aarch64|amd64|x86_64)
      if [ "$(cat "$CORES/melonds.version" 2>/dev/null)" = "$MELONDS" ] && [ -f "$CORES/melonds_libretro.so" ]; then
        echo "The DS emulator (melonDS) is built already."
      else
        step "Building the DS emulator (melonDS): $(how_long "about 10 minutes on a Pi 4, less on a Pi 5" "a few minutes")"
        build_melonds || echo "(Couldn't build melonDS: DS games won't start.)"
      fi ;;
    *) echo "(DS games need the 64-bit Raspberry Pi OS: no DS emulator on this one.)" ;;
  esac
else
  echo "(DS games need a Pi 4 or 5: no DS emulator on this one.)"
fi

# Dreamcast: Flycast, built here from its source, on a Pi 4 or 5 only (it draws in 3D with their graphics chip,
# OpenGL ES 3). It's built for this Pi's memory pages (a Pi 5's are bigger than a Pi 4's): moved to the other
# kind, it's built again. A Dreamcast's BIOS isn't needed (Flycast has its own); dc_boot.bin in ~/Games/BIOS is
# used if it's there
FLYCAST=v2.7
flycast_source() {  # flycast_source FOLDER
  local -x GIT_TERMINAL_PROMPT=0     # (a question from git would wait unseen: an error instead)
  local x86=""
  case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
    amd64|x86_64|i386|i686) x86=core/deps/xbyak ;;    # (a PC's quick way of running the Dreamcast's processor)
  esac
  # its source, and the parts it's built from (not what other systems need, nor its own window and menus)
  git -c advice.detachedHead=false clone -q --depth 1 --branch "$FLYCAST" https://github.com/flyinghead/flycast.git "$1/src" \
    && git -C "$1/src" submodule update -q --init --depth 1 --recursive -- core/deps/libchdr core/deps/tinygettext \
         core/deps/asio $x86
}
flycast_make() {   # flycast_make FOLDER JOBS (OpenGL ES 3, drawn in for media mode: no Vulkan)
  cmake -S "$1/src" -B "$1/build" -DCMAKE_BUILD_TYPE=Release -DLIBRETRO=ON -DUSE_GLES=ON -DUSE_VULKAN=OFF \
      -DUSE_LUA=OFF -DUSE_OPENMP=OFF \
    && make -C "$1/build" -j"$2" flycast_libretro
}
flycast_built() {  # what's noted once it's built: the version, and the memory pages it's for
  echo "$FLYCAST pages $(getconf PAGESIZE 2>/dev/null || echo 4096)"
}
build_flycast() {
  local jobs mem tmp so
  jobs=$(nproc 2>/dev/null || echo 1)
  mem=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
  if [ "$mem" -lt 1500 ]; then jobs=1; elif [ "$mem" -lt 3000 ] && [ "$jobs" -gt 2 ]; then jobs=2; fi
  apt-get install -y build-essential git cmake libgles-dev libegl-dev \
    libegl-mesa0 libgl1-mesa-dri libgbm1 || return 1                      # (Mesa too, to run it)
  tmp="$(mktemp -d /var/tmp/flycast-XXXXXX)" || return 1
  BUILDING="$tmp"
  working "Downloading" "$tmp/build.log" flycast_source "$tmp" \
    && working "Building" "$tmp/build.log" flycast_make "$tmp" "$jobs" \
    || { tail -n 20 "$tmp/build.log"; rm -rf "$tmp"; return 1; }
  so="$(find "$tmp/build" -name flycast_libretro.so | head -n 1)"
  install -d "$CORES" && install -m 644 "$so" "$CORES/" || { rm -rf "$tmp"; return 1; }
  flycast_built > "$CORES/flycast.version"
  rm -rf "$tmp"
}
if [ "$BIG" = yes ]; then
  if [ "$(cat "$CORES/flycast.version" 2>/dev/null)" = "$(flycast_built)" ] && [ -f "$CORES/flycast_libretro.so" ]; then
    echo "The Dreamcast emulator (Flycast) is built already."
  else
    step "Building the Dreamcast emulator (Flycast): $(how_long "about 20 minutes on a Pi 4, less on a Pi 5" "a few minutes")"
    build_flycast || echo "(Couldn't build Flycast: Dreamcast games won't start.)"
  fi
else
  echo "(Dreamcast games need a Pi 4 or 5: no Dreamcast emulator on this one.)"
fi

# Chromium, from Web's first page on a Pi 4 or 5: the whole web on the whole screen. cage shows it there with no
# desktop round it (through Xwayland, so it can be a TV's size), and wlr-randr gives it the size and turn media mode
# has. It runs as you, in a session of your own on a console of its own, and this is that session's PAM service:
# Pietato starts it (as root), so no password is asked.
if [ "$BIG" = yes ] && [ "$CASE" != 2w ]; then
  step "Installing Chromium, for the whole web from Web's first page (about 300 MB)"
  CHROMIUM_PKGS="chromium chromium-browser"     # (Debian's, or its older name)
  if grep -qx 'ID=ubuntu' "${PITATO_OS_RELEASE:-/etc/os-release}" 2>/dev/null; then   # (Ubuntu's: it puts in the
    CHROMIUM_PKGS=chromium-browser                                                    # chromium snap)
  fi
  chromium_install() {
    local pkg
    for pkg in $CHROMIUM_PKGS; do apt-get install -y "$pkg" && return 0; done
    return 1
  }
  if apt-get install -y cage xwayland wlr-randr fonts-liberation fonts-noto-color-emoji && chromium_install; then
    cat > /etc/pam.d/pietato-chromium <<'EOF'
# Pietato's Chromium: a session of your own on its console. Pietato starts it, as root, so no password is asked.
auth      required  pam_unix.so nullok
account   required  pam_unix.so
session   required  pam_unix.so
session   optional  pam_env.so readenv=1 envfile=/etc/default/locale
session   required  pam_systemd.so
EOF
  else
    echo "(Couldn't install Chromium: Web shows pages its own way.)"
  fi
fi

step "Installing LibreOffice (Word, Excel and PowerPoint files with their real layout; about 400 MB)"
apt-get install -y --no-install-recommends libreoffice-core libreoffice-writer \
  libreoffice-calc libreoffice-impress || echo "(Couldn't install LibreOffice: documents open as plain text.)"

# --------------------------------------------------------------------------
if [ "$GPI" = yes ] && [ "$CASE" = 2 ]; then
step "Building screen overlay (dpi24 without the dock and power switch pins)"
TMP="$(mktemp -d)"
# the case's screen is RGB666 on GPIOs 0-9, 12-17 and 20-25 (dpi_output_format 0x16): 18 says it's in the dock
# with the TV on, 26 and 27 are the power switch. On fb for the firmware's screen, on vc4 under fkms
cat > "$TMP/gpicase2-dpi.dts" <<'EOF'
/dts-v1/;
/plugin/;
/ {
    compatible = "brcm,bcm2835";
    fragment@0 {
        target = <&fb>;
        __overlay__ {
            pinctrl-names = "default";
            pinctrl-0 = <&gpicase2_dpi_pins>;
        };
    };
    fragment@1 {
        target = <&vc4>;
        __overlay__ {
            pinctrl-names = "default";
            pinctrl-0 = <&gpicase2_dpi_pins>;
        };
    };
    fragment@2 {
        target = <&gpio>;
        __overlay__ {
            gpicase2_dpi_pins: gpicase2_dpi_pins {
                brcm,pins = <0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 20 21 22 23 24 25>;
                brcm,function = <6>;
                brcm,pull = <0>;
            };
        };
    };
};
EOF
dtc -@ -q -I dts -O dtb -o "$BOOT/overlays/gpicase2-dpi.dtbo" "$TMP/gpicase2-dpi.dts"
# in the dock, the TV taken as plugged in: KMS goes by the CM4's own HDMI hotplug line, which the dock may not pass on
# (RetroFlag's settings force it too; hdmi_force_hotplug is the firmware's alone)
cat > "$TMP/gpicase2-tv.dts" <<'EOF'
/dts-v1/;
/plugin/;
/ {
    compatible = "brcm,bcm2711";
    fragment@0 {
        target-path = "/chosen";
        __overlay__ {
            bootargs = "vc4.force_hotplug=1";
        };
    };
};
EOF
dtc -@ -q -I dts -O dtb -o "$BOOT/overlays/gpicase2-tv.dtbo" "$TMP/gpicase2-tv.dts"
rm -rf "$TMP"

# --------------------------------------------------------------------------
step "Updating $CONFIG (backup saved next to it)"
cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d-%H%M%S)"

# remove this script's old block
sed -i '/^# >>> gpi-case setup >>>/,/^# <<< gpi-case setup <<</d' "$CONFIG"
# remove settings added by hand earlier (RetroFlag's patch for the case, say), so nothing is duplicated: its screen
# and fkms go in the part for the case's screen, KMS in the part for the TV
sed -i -E '/^\s*dtoverlay=(dpi24|gpicase-dpi|gpicase2-dpi|gpicase2-tv|audremap|vc4-fkms-v3d)/d;
           /^\s*(enable_dpi_lcd|display_default_lcd|dpi_group|dpi_mode|dpi_output_format|hdmi_timings|framebuffer_width|framebuffer_height)=/d;
           /^\s*dtoverlay=gpio-shutdown.*gpio_pin=26/d;
           /^\s*gpio=(27=op,dh|18=ip,pd)/d;
           /^\s*disable_audio_dither=/d;
           /^# GPi Case 2W screen/d;
           /^# case speaker/d' "$CONFIG"
sed -i -E 's/^\s*dtoverlay=vc4-kms-v3d/#dtoverlay=vc4-kms-v3d/' "$CONFIG"
USB_ON=""       # the case's buttons and sound are on the CM4's USB, which needs turning on (Bookworm's config.txt does,
                # in its [cm4] part; RetroFlag's patch with dwc2): a line for any Pi, [all], [pi4] or [cm4] does it
if ! awk '/^[[:space:]]*\[/ { part = $0 }
          /^[[:space:]]*(otg_mode=1|dtoverlay=dwc2)/ && (part == "" || part ~ /^[[:space:]]*\[(all|pi4|cm4)\]/) { on = 1 }
          END { exit !on }' "$CONFIG"; then
  USB_ON=$'# the case\'s buttons and sound are on the CM4\'s USB: on\notg_mode=1\n'
fi

{
cat <<'EOF'
# >>> gpi-case setup >>>
[all]
# GPi Case 2 (CM4): the case's screen, or the TV through its dock, picked as the Pi starts. GPIO 18 is high in
# the dock with the TV on (as RetroFlag's own script reads it); Pietato restarts the Pi when that changes.
gpio=18=ip,pd
EOF
printf '%s' "$USB_ON"
cat <<'EOF'
# the power switch: GPIO 27 keeps the case on while the Pi shuts down, and switching off (GPIO 26 goes low)
# shuts it down safely. The case's SAFE SHUTDOWN switch goes to ON.
gpio=27=op,dh
dtoverlay=gpio-shutdown,gpio_pin=26,active_low=1,gpio_pull=up
[gpio18=0]
# the case's screen (RetroFlag's settings for it), the 3D chip on for N64 and PSP games (fkms), and the sound
# through the case's own (USB) sound
dtoverlay=vc4-fkms-v3d
dtoverlay=gpicase2-dpi
enable_dpi_lcd=1
display_default_lcd=1
dpi_group=2
dpi_mode=87
dpi_output_format=0x00016
hdmi_timings=640 0 41 40 41 480 0 18 9 18 0 0 0 60 0 24000000 1
framebuffer_width=640
framebuffer_height=480
disable_overscan=1
dtparam=audio=off
[gpio18=1]
# in the dock: the TV, as on any Pi on HDMI (the dock's HDMI taken as plugged in, as RetroFlag's settings have it)
dtoverlay=vc4-kms-v3d
dtoverlay=gpicase2-tv
hdmi_force_hotplug=1
[all]
# <<< gpi-case setup <<<
EOF
} >> "$CONFIG"

# RetroFlag's own scripts for the case would fight over the same pins, and swap config.txt for theirs
if [ -f /etc/rc.local ] && grep -qE '^[^#]*RetroFlag/(SafeShutdown\.py|lcdfirst\.sh)' /etc/rc.local; then
  sed -i -E 's@^([^#]*RetroFlag/(SafeShutdown\.py|lcdfirst\.sh).*)$@# \1   # (Pietato looks after the case)@' /etc/rc.local
  echo "Turned off RetroFlag's scripts in /etc/rc.local: Pietato looks after the case."
fi

elif [ "$GPI" = yes ]; then
step "Building screen overlay (dpi24 without the speaker and power switch pins)"
TMP="$(mktemp -d)"
cat > "$TMP/gpicase-dpi.dts" <<'EOF'
/dts-v1/;
/plugin/;
/ {
    compatible = "brcm,bcm2835";
    fragment@0 {
        target = <&fb>;
        __overlay__ {
            pinctrl-names = "default";
            pinctrl-0 = <&gpicase_dpi_pins>;
        };
    };
    fragment@1 {
        target = <&vc4>;
        __overlay__ { status = "disabled"; };
    };
    fragment@2 {
        target = <&gpio>;
        __overlay__ {
            gpicase_dpi_pins: gpicase_dpi_pins {
                brcm,pins = <0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 20 21 22 23 24 25>;
                brcm,function = <6>;
                brcm,pull = <0>;
            };
        };
    };
};
EOF
dtc -@ -q -I dts -O dtb -o "$BOOT/overlays/gpicase-dpi.dtbo" "$TMP/gpicase-dpi.dts"
rm -rf "$TMP"

# --------------------------------------------------------------------------
step "Updating $CONFIG (backup saved next to it)"
cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d-%H%M%S)"

# remove this script's old block
sed -i '/^# >>> gpi-case setup >>>/,/^# <<< gpi-case setup <<</d' "$CONFIG"
# remove settings added by hand earlier, so nothing is duplicated
sed -i -E '/^\s*dtoverlay=(dpi24|gpicase-dpi|audremap)/d;
           /^\s*(enable_dpi_lcd|display_default_lcd|dpi_group|dpi_mode|dpi_output_format|hdmi_timings|framebuffer_width|framebuffer_height)=/d;
           /^\s*dtoverlay=gpio-shutdown.*gpio_pin=26/d;
           /^\s*gpio=27=op,dh/d;
           /^\s*disable_audio_dither=/d;
           /^# GPi Case 2W screen/d;
           /^# case speaker/d' "$CONFIG"
# the legacy screen settings only work with KMS off
sed -i -E 's/^\s*dtoverlay=vc4-kms-v3d/#dtoverlay=vc4-kms-v3d/' "$CONFIG"

cat >> "$CONFIG" <<'EOF'
# >>> gpi-case setup >>>
[all]
# GPi Case 2W screen
dtoverlay=gpicase-dpi
enable_dpi_lcd=1
display_default_lcd=1
dpi_group=2
dpi_mode=87
dpi_output_format=0x00016
hdmi_timings=640 0 1 1 20 480 0 1 1 2 0 0 0 60 0 19200000 1
framebuffer_width=640
framebuffer_height=480
disable_overscan=1
# GPi Case 2W speaker (PWM on GPIO 18/19); no hiss under quiet sound
dtparam=audio=on
dtoverlay=audremap,pins_18_19,enable_jack
disable_audio_dither=1
# GPi Case 2W power switch: GPIO 27 keeps the case on while the Pi shuts down, and
# switching off (GPIO 26 goes low) shuts it down safely. The case's SAFE SHUTDOWN
# switch, behind the cartridge, goes to ON.
gpio=27=op,dh
dtoverlay=gpio-shutdown,gpio_pin=26,active_low=1,gpio_pull=up
# <<< gpi-case setup <<<
EOF

# RetroFlag's own safe-shutdown script would fight over the same pins
if [ -f /etc/rc.local ] && grep -qE '^[^#]*RetroFlag/SafeShutdown\.py' /etc/rc.local; then
  sed -i -E 's|^([^#]*RetroFlag/SafeShutdown\.py.*)$|# \1   # (Pietato looks after the power switch)|' /etc/rc.local
  echo "Turned off RetroFlag's SafeShutdown.py in /etc/rc.local: Pietato looks after the power switch."
fi

else
  if grep -q '^# >>> gpi-case setup >>>' "$CONFIG" 2>/dev/null; then     # (a PC has no config.txt)
    step "Taking the GPi Case settings out of $CONFIG (backup saved next to it)"
    cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d-%H%M%S)"
    sed -i '/^# >>> gpi-case setup >>>/,/^# <<< gpi-case setup <<</d' "$CONFIG"
    # HDMI screens need KMS, which the case's settings had turned off
    sed -i -E 's/^#dtoverlay=vc4-kms-v3d/dtoverlay=vc4-kms-v3d/' "$CONFIG"
  fi
  # (the screen's own resolution, as it is: Settings > Resolution changes it)
fi

# --------------------------------------------------------------------------
step "Installing the controller and media script"
install -m 755 "$HERE/pitato.py" /usr/local/bin/pitato.py        # (it starts the rest: the Pietato folder)
rm -rf /usr/local/share/pitato/pitato                          # (a fresh copy: no old files left in it)
install -d /usr/local/share/pitato/pitato/screens
install -m 644 "$HERE"/pitato/*.py /usr/local/share/pitato/pitato/
install -m 644 "$HERE"/pitato/screens/*.py /usr/local/share/pitato/pitato/screens/
python3 -m compileall -q /usr/local/share/pitato/pitato > /dev/null || true   # (quicker to start)

grep -qx uinput /etc/modules || echo uinput >> /etc/modules
modprobe uinput || true

cat > /etc/systemd/system/pitato.service <<EOF
[Unit]
Description=Pietato: controller buttons as keys, and media mode
After=multi-user.target

[Service]
Environment="PITATO_STATIC=$UNIT_STATIC"
ExecStart=/usr/bin/python3 /usr/local/bin/pitato.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable pitato            # (started at the end: media mode would cover these questions)
if [ -f /etc/systemd/system/gpi-keys.service ]; then
  systemctl disable gpi-keys 2>/dev/null || true   # (Pietato by the name it had before: it goes at the end)
fi

# --------------------------------------------------------------------------
# the console signs you in by itself at start-up (what raspi-config calls Console Autologin), so
# after a reboot it's ready to use; --login puts the password prompt back
AUTOLOGIN=/etc/systemd/system/getty@tty1.service.d/autologin.conf
KEEP_LOGIN=/var/lib/pitato/keep-login     # (--login is remembered for the next time it's run)
if [ "$LOGIN" = yes ]; then
  install -d /var/lib/pitato
  touch "$KEEP_LOGIN"
  if [ -f "$AUTOLOGIN" ]; then
    step "The console asks for your password at start-up again"
    rm -f "$AUTOLOGIN"
    systemctl daemon-reload
  fi
elif [ -f "$KEEP_LOGIN" ] || [ -f /var/lib/gpi-keys/keep-login ]; then
  :                                         # (you asked for the password prompt before)
elif [ "$USER_NAME" != root ] && id "$USER_NAME" >/dev/null 2>&1; then
  step "Signing $USER_NAME in by itself at start-up (sudo bash setup.sh --login undoes it)"
  install -d /etc/systemd/system/getty@tty1.service.d
  cat > "$AUTOLOGIN" <<AUTO
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER_NAME --noclear %I \$TERM
AUTO
  systemctl daemon-reload
fi

# --------------------------------------------------------------------------
# A PC with a desktop (Ubuntu Desktop's): it starts in the terminal instead, with Pietato on the screen, as a Pi does.
# System > Desktop starts the desktop when you want it, and the computer restarting comes back to Pietato. (Not on
# an update: you may have set it back yourself.)
if [ "$PC" = yes ] && [ "$UPDATE" != yes ] && [ "$(systemctl get-default 2>/dev/null)" = graphical.target ]; then
  step "This computer starts in Pietato now, not the desktop (System > Desktop starts the desktop)"
  systemctl set-default multi-user.target
fi

# --------------------------------------------------------------------------
step "Installing the web page (port 5432, and 5443 for its secure page)"
install -d /usr/local/share/pitato/templates
install -m 644 "$HERE/pitato/webui.py" /usr/local/share/pitato/
install -m 644 "$HERE/pitato/coder_hooks.py" /usr/local/share/pitato/    # (the page hands it to Claude Code's computer)
install -m 644 "$HERE/templates/index.html" "$HERE/templates/play.html" "$HERE/templates/play.js" \
  /usr/local/share/pitato/templates/                                     # (play: a game on your phone, Play here)
install -d /usr/local/share/pitato/static/fonts    # the typefaces: the page's, and the home screen's (without them: the system's)
for f in "$HERE"/static/fonts/*; do
  if [ -f "$f" ]; then install -m 644 "$f" /usr/local/share/pitato/static/fonts/; fi
done
rm -rf /usr/local/share/pitato/index.html /usr/local/share/pitato/fonts    # (where they were before)

cat > /etc/systemd/system/pitato-web.service <<WEBUI
[Unit]
Description=Pietato web page: the screen and your files (port 5432; 5443, its secure page)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$USER_HOME
Environment="PITATO_STATIC=$UNIT_STATIC"
ExecStart=/usr/bin/python3 /usr/local/share/pitato/webui.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
WEBUI
systemctl daemon-reload
systemctl enable pitato-web

# settings files an earlier version kept in your home folder go in the static folder now: with the
# web page stopped meanwhile, as until it restarts it would look for its password in the old place
systemctl stop pitato-web 2>/dev/null || true
if [ -f /etc/systemd/system/gpi-webui.service ]; then  # (the web page by the name it had before Pietato's)
  systemctl disable --now gpi-webui 2>/dev/null || true
  rm -f /etc/systemd/system/gpi-webui.service
  systemctl daemon-reload
fi
rm -rf "$USER_HOME/.cache/gpi-media"                  # (its small copies of your pictures: made again)
settings_folder radio.txt streams.txt streams.m3u crypto.txt camera.txt bot.txt \
  homeassistant.txt webui.txt plex.txt
if [ ! -e "$STATIC/bot.txt" ]; then
  settings_folder friend.txt                        # the bot's settings, by their earlier name
fi

# Sound here and Mic here (the web page): the Pi's sound on your phone or computer, and its microphone the bot's.
# Both go through the Loopback sound card (snd-aloop), card 7 so it's never the Pi's own sound (a Pi's kernel has
# room for cards 0 to 7 only); media mode plays into it mixed (pietato_web), and the web page (in the audio group)
# hands out what comes out of it.
cat > /etc/modprobe.d/pietato-loopback.conf <<'ALOOP'
# Pietato's web page: Sound here and Mic here go through this card
options snd-aloop index=7 id=Loopback pcm_substreams=2
ALOOP
echo snd-aloop > /etc/modules-load.d/pietato-loopback.conf
if ! modprobe snd-aloop 2>/dev/null; then
  if [ "$PC" = yes ]; then                         # (Ubuntu keeps it in its kernel's extra modules)
    apt-get install -y "linux-modules-extra-$(uname -r)" > /dev/null 2>&1 || true
  fi
  modprobe snd-aloop 2>/dev/null || echo "(The Loopback sound card didn't load yet: Sound here and Mic here work after a restart.)"
fi
if command -v wireplumber > /dev/null 2>&1; then   # (a desktop's PipeWire leaves the card alone: it's not a speaker)
  install -d /etc/wireplumber/main.lua.d /etc/wireplumber/wireplumber.conf.d
  cat > /etc/wireplumber/main.lua.d/51-pietato-loopback.lua <<'WPLUA'
-- Pietato: the Loopback card is the web page's (Sound here, Mic here), not a speaker or a microphone of yours
table.insert(alsa_monitor.rules, {
  matches = { { { "device.name", "matches", "alsa_card.platform-snd_aloop.*" } } },
  apply_properties = { ["device.disabled"] = true },
})
WPLUA
  cat > /etc/wireplumber/wireplumber.conf.d/51-pietato-loopback.conf <<'WPCONF'
# Pietato: the Loopback card is the web page's (Sound here, Mic here), not a speaker or a microphone of yours
monitor.alsa.rules = [
  {
    matches = [ { device.name = "~alsa_card.platform-snd_aloop.*" } ]
    actions = { update-props = { device.disabled = true } }
  }
]
WPCONF
fi
install -d /etc/alsa/conf.d
cat > /etc/alsa/conf.d/60-pietato-web.conf <<'WEBPCM'
# Pietato: the Pi's sound for the web page's Sound here, mixed into the Loopback card (webui.py hands it out)
pcm.pietato_web {
    type plug
    slave.pcm "pietato_web_mix"
}
pcm.pietato_web_mix {
    type dmix
    ipc_key 54320
    ipc_key_add_uid false
    ipc_perm 0666
    slave {
        pcm "hw:Loopback,0,0"
        format S16_LE
        rate 48000
        channels 2
        period_size 1024
        buffer_size 4096
    }
}
WEBPCM
if [ "$USER_NAME" != root ]; then
  usermod -aG audio "$USER_NAME" || true
fi
systemctl restart pitato-web || true

# --------------------------------------------------------------------------
# a version with YouTube installed yt-dlp (in /opt/gpi-media), a user for it and a daily update:
# take them away (never a gpi-media folder cloned there)
if [ -f /etc/systemd/system/gpi-ytdlp-update.timer ] || [ -d /opt/gpi-media/venv ]; then
  step "Taking out what the YouTube version installed"
  systemctl disable --now gpi-ytdlp-update.timer 2>/dev/null || true
  rm -f /etc/systemd/system/gpi-ytdlp-update.timer /etc/systemd/system/gpi-ytdlp-update.service
  systemctl daemon-reload
  if [ ! -e /opt/gpi-media/.git ] && [ "$HERE" != /opt/gpi-media ]; then
    rm -rf /opt/gpi-media/venv /opt/gpi-media/node
    rmdir /opt/gpi-media 2>/dev/null || true
  fi
  rm -rf /var/cache/gpi-media /var/lib/pitato/youtube.json /var/lib/gpi-keys/youtube.json
  if id gpi-media >/dev/null 2>&1; then userdel gpi-media || true; fi
fi

# --------------------------------------------------------------------------
step "Making $USER_HOME/Videos, Music, Pictures, Documents and Games, and your settings in $STATIC"
mkdir -p "$USER_HOME/Videos" "$USER_HOME/Music" "$USER_HOME/Pictures" "$USER_HOME/Documents" "$USER_HOME/Games" \
  "$USER_HOME/Games/BIOS"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/Videos" "$USER_HOME/Music" "$USER_HOME/Pictures" \
  "$USER_HOME/Documents" "$USER_HOME/Games" "$USER_HOME/Games/BIOS"
GAME_FOLDERS="gb gbc gba nes snes genesis sms gg ps1"
case "$MODEL" in *"Pi 4"*|*"Pi 5"*|*"Compute Module 4"*|*"Compute Module 5"*) GAME_FOLDERS="$GAME_FOLDERS n64 psp nds dc" ;; esac
if [ "$PC" = yes ]; then GAME_FOLDERS="$GAME_FOLDERS n64 psp nds dc"; fi
for sys in $GAME_FOLDERS; do                       # a folder for each kind of game, so it's clear where they go
  if [ ! -d "$USER_HOME/Games/$sys" ]; then
    mkdir "$USER_HOME/Games/$sys" && chown "$USER_NAME:$USER_NAME" "$USER_HOME/Games/$sys"
  fi
done
if [ ! -f "$STATIC/streams.txt" ]; then
  cat > "$STATIC/streams.txt" <<'STREAMS'
# Streams tab in media mode. One per line:   Name | URL
# Works with direct video/audio links and HLS (.m3u8) streams.
# You can also save an .m3u playlist as streams.m3u next to this file instead.
#
# Example:
# My Channel | https://example.com/live/stream.m3u8
STREAMS
  chown "$USER_NAME:$USER_NAME" "$STATIC/streams.txt"
fi

# --------------------------------------------------------------------------
if [ ! -f "$STATIC/radio.txt" ]; then
  cat > "$STATIC/radio.txt" <<'RADIO'
# Extra stations for the Radio tab. One per line:   Name | URL
# The Radio tab already has stations by genre, search and Radio Paradise;
# press Y on any station there to add it here.
#
# Example:
# My Station | http://example.com/stream.mp3
RADIO
  chown "$USER_NAME:$USER_NAME" "$STATIC/radio.txt"
fi

# --------------------------------------------------------------------------
# the Finance tab's stocks and coins to start with (Y on the tab adds more), quietly; an old crypto.txt (the Crypto
# tab's, from before it was Finance) moved across. No cameras: they're added later, on the Camera tab.
FIN_HEAD="# Finance: stocks by their tickers, as on finance.yahoo.com (AAPL, AMZN, TSLA), and coins by their
# CoinGecko ids, as in coingecko.com/en/coins/bitcoin. Y on the Finance tab looks them up and adds
# them, or removes them."
if [ ! -f "$STATIC/finance.txt" ]; then
  if [ -f "$STATIC/crypto.txt" ]; then
    { echo "$FIN_HEAD"
      grep -qiE '^[[:space:]]*stocks[[:space:]]*=' "$STATIC/crypto.txt" || echo "stocks = AAPL, AMZN, TSLA"
      grep -vE '^[[:space:]]*#' "$STATIC/crypto.txt" || true
    } > "$STATIC/finance.txt"
    chown "$USER_NAME:$USER_NAME" "$STATIC/finance.txt"
    rm -f "$STATIC/crypto.txt"
  else
    cat > "$STATIC/finance.txt" <<FINANCE
$FIN_HEAD
stocks = AAPL, AMZN, TSLA
coins = bitcoin, ethereum, dogecoin
FINANCE
    chown "$USER_NAME:$USER_NAME" "$STATIC/finance.txt"
  fi
fi

# --------------------------------------------------------------------------
step "Bluetooth"
if ! command -v rfkill > /dev/null 2>&1; then    # (Ubuntu Server's hasn't it: Pietato turns Bluetooth back on with it)
  apt-get install -y rfkill > /dev/null 2>&1 || true
fi
rfkill unblock bluetooth 2>/dev/null || true
if [ -f /etc/bluetooth/main.conf ]; then
  if grep -qE '^\s*#?\s*AutoEnable' /etc/bluetooth/main.conf; then
    sed -i -E 's/^\s*#?\s*AutoEnable\s*=.*/AutoEnable=true/' /etc/bluetooth/main.conf
  else
    sed -i '/^\[Policy\]/a AutoEnable=true' /etc/bluetooth/main.conf
  fi
fi
systemctl enable --now bluetooth || true
# Bluetooth headphones and speakers: BlueALSA plays through them (with Settings > Sound on Auto, sound goes to
# them while they're connected). Only as the player (A2DP source): the Pi isn't a speaker for your phone. Left
# out where PipeWire or PulseAudio looks after Bluetooth's sound (a desktop): the two would trip over each other.
if command -v wireplumber >/dev/null 2>&1 || command -v pulseaudio >/dev/null 2>&1; then
  echo "(PipeWire or PulseAudio has Bluetooth's sound on this $MACHINE: BlueALSA left out.)"
elif apt-get install -y bluez-alsa-utils libasound2-plugin-bluez && command -v bluealsa >/dev/null 2>&1; then
  install -d /etc/systemd/system/bluealsa.service.d
  cat > /etc/systemd/system/bluealsa.service.d/pitato.conf <<BLUEALSA
# Pietato (setup.sh): sound to Bluetooth headphones and speakers, the Pi as the player
[Service]
ExecStart=
ExecStart=$(command -v bluealsa) -p a2dp-source
BLUEALSA
  systemctl daemon-reload
  systemctl enable bluealsa 2>/dev/null || true
  systemctl restart bluealsa || echo "(BlueALSA didn't start: sound may not play through Bluetooth headphones.)"
else
  echo "(Couldn't install BlueALSA: sound won't play through Bluetooth headphones.)"
fi
echo "Pair Bluetooth controllers, keyboards, headphones and the rest in Settings > Bluetooth, or on the web page."

# --------------------------------------------------------------------------
step "TV Remote through Home Assistant (optional)"
if grep -qE '^\s*token\s*=\s*\S' "$STATIC/homeassistant.txt" 2>/dev/null; then
  echo "Keeping your existing $STATIC/homeassistant.txt"
elif [ "$UPDATE" = yes ] || [ "$IMAGE" = yes ]; then
  echo "No Home Assistant yet: add it any time in its Settings, on the $MACHINE or the web page."
else
  echo "The Home tab's TV Remote and Lights work through Home Assistant. You can add it now,"
  echo "or later in its Settings, on the $MACHINE or the web page (easier for pasting the token)."
  echo "Make a token in Home Assistant: your profile > Security > Long-lived access tokens."
  read -r -p "Home Assistant address, e.g. homeassistant.local:8123 (blank to skip): " ha_url
  if [ -n "$ha_url" ]; then
    read -r -s -p "Long-lived access token (hidden as you paste): " ha_token
    echo
    read -r -p "TV entity, e.g. media_player.living_room_tv (Enter to find it): " ha_tv
    ( umask 077
      cat > "$STATIC/homeassistant.txt" <<HA
# TV Remote and Lights: your Home Assistant and a long-lived access token. Keep this file private.
url = $ha_url
token = $ha_token
# Optional. Found by themselves when blank:
tv = $ha_tv
remote =
# How the TV names its buttons: samsung, android, roku, apple or lg
style =
HA
    )
    chown "$USER_NAME:$USER_NAME" "$STATIC/homeassistant.txt"
    chmod 600 "$STATIC/homeassistant.txt"
  fi
fi

# --------------------------------------------------------------------------
# a camera server from before Pietato had its name: under the new one
if [ -f /etc/systemd/system/gpi-camera.service ] && [ -f "$HERE/pitato/camera.py" ]; then
  install_camera
fi

# Pietato by the name it had before (gpi-media): its service stops (it answered the questions above),
# its old files go, and what it kept (your settings, sign-ins, voices) moves across
retire_old() {
  if [ -f /etc/systemd/system/gpi-keys.service ]; then
    systemctl disable --now gpi-keys 2>/dev/null || true
    rm -f /etc/systemd/system/gpi-keys.service
    systemctl daemon-reload
  fi
  rm -f /usr/local/bin/gpi_keys.py
  local old new f
  for old in /var/lib/gpi-keys /var/cache/gpi-keys; do
    [ -d "$old" ] || continue
    new="${old%/gpi-keys}/pitato"
    install -d "$new"
    for f in "$old"/* "$old"/.[!.]*; do
      [ -e "$f" ] || continue
      if [ -e "$new/$(basename "$f")" ]; then rm -rf "$f"; else mv "$f" "$new/" || true; fi
    done
    rmdir "$old" 2>/dev/null || true
  done
  if [ -d /usr/local/share/gpi-media ]; then
    for f in piper voices; do                       # (the bot's voice: not fetched again)
      if [ -d "/usr/local/share/gpi-media/$f" ] && [ ! -e "/usr/local/share/pitato/$f" ]; then
        mv "/usr/local/share/gpi-media/$f" /usr/local/share/pitato/ || true
      fi
    done
    rm -rf /usr/local/share/gpi-media
  fi
}

FINISHED=yes
let_go             # (done: the power button shuts it down again)
if [ "$IMAGE" = yes ]; then
  install -d /var/lib/pitato             # (what's put in, for Update software)
  git -c safe.directory='*' -C "$HERE" rev-parse HEAD > /var/lib/pitato/installed-commit
  retire_old
  echo
  echo "All set, for the image (nothing started: it starts on the Pi it's written for)."
  exit 0
fi
echo
if [ "$GPI" = yes ]; then
  echo "All set. Reboot to apply the screen and audio settings."
else
  echo "All set. Reboot to start."
fi
if [ "$PC" = yes ] && [ -e /etc/systemd/system/display-manager.service ]; then
  echo "This computer starts in Pietato. System > Desktop starts the desktop, and restarting comes back to Pietato."
fi
echo "It starts on the home screen (Settings > At start-up can make it the terminal)."
if [ -f "$AUTOLOGIN" ]; then
  echo "It signs you in by itself at start-up: no password needed at the console."
fi
echo "On your phone or computer, open  http://$(hostname).local:5432"
echo "to see the screen, work it with a remote, and add files."
echo "Your settings files are in $STATIC"
# what's put in now (git's id for it), for System > Update software: an update that got no further than git pull
# is offered again, to finish
install -d /var/lib/pitato
if [ -d "$HERE/.git" ] && command -v git > /dev/null \
   && git -c safe.directory='*' -C "$HERE" rev-parse HEAD > /var/lib/pitato/installed-commit.new 2> /dev/null; then
  mv -f /var/lib/pitato/installed-commit.new /var/lib/pitato/installed-commit
else
  rm -f /var/lib/pitato/installed-commit.new /var/lib/pitato/installed-commit
fi
if [ "$UPDATE" = yes ]; then
  retire_old
  exit 0           # (Update software restarts the Pi now)
fi
read -r -p "Reboot now? [Y/n] " ans
retire_old
if [[ ! "$ans" =~ ^[Nn] ]]; then
  reboot
else
  systemctl restart pitato || true
fi
