#!/usr/bin/env bash
# setup.sh - set up Raspberry Pi OS Lite (Bookworm) on any Raspberry Pi with a screen
#   - in a RetroFlag GPi Case 2W (Pi Zero 2 W): the case screen as the console (with
#     GPIO 18/19 left free for the speaker), the case speaker, and its power switch:
#     switching off shuts the Pi down safely (GPIO 26 and 27, as RetroFlag's own script)
#   - on any other Pi: the screen on HDMI as it is
#   - game controller buttons as keys + media mode (the case buttons, or any USB or
#     Bluetooth controller), which opens at start-up on a home screen of app icons: TV (Plex,
#     cartoons, free movies, news, sports, streams, a TV remote through Home Assistant),
#     music, radio, photos (filters, delete), videos, weather, stock and coin prices and charts,
#     a file browser for PDFs/documents/text, cameras on your other Pis (see
#     --camera below) with OBSBOT steering and pictures, a bot (Ollama on another
#     computer, a Piper voice on the Pi; at work it acts out your coding agent and sends
#     it your prompts), a Simulator (rock paper scissors, the game of life, orbits, forest
#     fire, the Mandelbrot set to tour or explore), Snake and your own Game Boy, Game Boy
#     Advance, NES, SNES, Genesis, Master System, Game Gear, PlayStation and (on a Pi 4 or
#     5) N64, PSP and DS games, two players on two controllers (mGBA, Nestopia, Snes9x,
#     Genesis Plus GX, and PCSX ReARMed, Mupen64Plus-Next, PPSSPP and melonDS built here),
#     system info, and settings (WiFi, Bluetooth and its headphones, background, colours,
#     location, sound, controller, bot...)  (pitato.py and the pitato folder, run at boot)
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
#   --gpi       it's in a GPi Case 2W (don't ask)
#   --no-gpi    it isn't (don't ask)
#   --login     keep asking for your password at start-up (instead of signing you in by itself)
#   --camera    only share this Pi's USB camera on the network, for Pitato's Camera tab on
#               another Pi (camera.py, port 5433); nothing else is installed
#   --update    no questions: it's set up as it was before (System > Update software runs it
#               after git pull, then restarts the Pi itself)
# Safe to run again: it replaces its own settings instead of adding duplicates.

set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo bash setup.sh"
  exit 1
fi

GPI=""
CAMERA=no
LOGIN=no
UPDATE=no
for arg in "$@"; do
  case "$arg" in
    --gpi) GPI=yes ;;
    --no-gpi) GPI=no ;;
    --login) LOGIN=yes ;;
    --camera) CAMERA=yes ;;
    --update) UPDATE=yes ;;
    *) echo "Unknown option: $arg (use --gpi, --no-gpi, --login, --camera or --update)"; exit 1 ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
STATIC="$HERE/static"                  # your settings files
case "$HERE" in
  *[\"\\]*) echo "Move the pitato folder somewhere without quotes or backslashes in its path."; exit 1 ;;
esac
if [ "$HERE" = "$USER_HOME" ] || [ "$HERE" = / ]; then
  echo "Keep pitato in a folder of its own (git clone makes one), not in $HERE itself."
  exit 1
fi
UNIT_STATIC="${STATIC//%/%%}"          # (as a systemd unit writes it)
if id "$USER_NAME" >/dev/null 2>&1 && command -v runuser >/dev/null \
   && ! runuser -u "$USER_NAME" -- test -r "$HERE" -a -x "$HERE"; then
  echo "$USER_NAME can't open $HERE, so the web page couldn't reach your settings in it."
  echo "Clone pitato into $USER_HOME and run setup.sh from there."
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
      line="  ${marks:i++%4:1} $what$pct  $(elapsed "$t")  Still working: leave the Pi on"
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
# the camera server (camera.py, port 5433): this Pi's USB camera, for Pitato's Camera tab on another Pi
install_camera() {
  step "Installing the camera server (this Pi's USB camera, port 5433)"
  apt-get update
  apt-get install -y ffmpeg v4l-utils python3
  install -d /usr/local/share/pitato
  install -m 644 "$HERE/pitato/camera.py" /usr/local/share/pitato/camera.py
  settings_folder camera-server.txt
  usermod -aG video "$USER_NAME" || true
  if [ -f /etc/systemd/system/gpi-camera.service ]; then     # (by the name it had before Pitato's)
    systemctl disable --now gpi-camera 2>/dev/null || true
    rm -f /etc/systemd/system/gpi-camera.service /usr/local/share/gpi-media/camera.py
    rmdir /usr/local/share/gpi-media 2>/dev/null || true
  fi
  cat > /etc/systemd/system/pitato-camera.service <<CAMSVC
[Unit]
Description=Pitato camera server: this Pi's USB camera on the network (port 5433)
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
    echo "pitato/camera.py isn't here. Run this from the pitato folder."
    exit 1
  fi
  install_camera
  echo
  echo "Done. On Pitato's Camera tab, add this Pi:  $(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "It also shows up there by itself, under On your network."
  echo "To see the picture in a browser:  http://$(hostname).local:5433"
  exit 0
fi

for f in pitato.py pitato/app.py pitato/webui.py pitato/coder_hooks.py templates/index.html; do
  if [ ! -f "$HERE/$f" ]; then
    echo "$f isn't here. Run this from the pitato folder."
    exit 1
  fi
done

# Until it's done, a shutdown asked for gently (a Pi 5's power button, the GPi Case's switch, poweroff without
# sudo) waits. Nothing can stop a pulled plug, so it says to leave the Pi on. If it stops early (an error, Ctrl+C),
# it says so, and clears away the emulator it was partway through building
FINISHED=no
BUILDING=""        # (that emulator's folder in /var/tmp)
HOLD=""
if command -v systemd-inhibit > /dev/null 2>&1; then
  systemd-inhibit --what=shutdown:sleep:handle-power-key --mode=block --who="Pitato setup" \
    --why="Setting up Pitato: leave the Pi on until it says All set" \
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


if [ -d /boot/firmware ]; then BOOT=/boot/firmware; else BOOT=/boot; fi
CONFIG="$BOOT/config.txt"

# --------------------------------------------------------------------------
# the GPi Case 2W needs its own screen and speaker settings; any other Pi uses HDMI
MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)"
SLOW=no         # Pi Zero, 1, 2 and 3: video on a big TV is smoother at 720p
case "$MODEL" in
  *Zero*|"Raspberry Pi 3"*|"Raspberry Pi 2"*|"Raspberry Pi Model"*|"Raspberry Pi Compute Module 3"*) SLOW=yes ;;
esac
if [ -z "$GPI" ] && [ "$UPDATE" = yes ]; then       # (as it was set up: the case's settings there, or not)
  if grep -q '^# >>> gpi-case setup >>>' "$CONFIG" 2>/dev/null; then GPI=yes; else GPI=no; fi
fi
if [ -z "$GPI" ]; then
  if [[ "$MODEL" == *Zero* ]] || grep -q '^# >>> gpi-case setup >>>' "$CONFIG" 2>/dev/null; then
    read -r -p "Is this Pi in a RetroFlag GPi Case 2W? [Y/n] " ans
    if [[ "$ans" =~ ^[Nn] ]]; then GPI=no; else GPI=yes; fi
  else
    GPI=no      # the case only takes a Pi Zero
  fi
fi
if [ "$GPI" = yes ]; then
  echo "Setting up for the GPi Case 2W: its screen, speaker and buttons."
else
  echo "Setting up for a screen on HDMI${MODEL:+ ($MODEL)}. Plug in any USB or Bluetooth game controller."
fi
echo "The first time takes a while: an hour or more on a Pi 4, as it builds the game emulators."
echo "Leave the Pi on until it says All set."

# --------------------------------------------------------------------------
step "Installing packages"
apt-get update
apt-get install -y python3-evdev python3-pil python3-numpy fonts-dejavu-core \
  mplayer poppler-utils iw evtest device-tree-compiler python3-flask alsa-utils ffmpeg bluez
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
      esac ;;
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
  step "Building the PlayStation emulator (PCSX ReARMed): a few minutes, longer on a Pi Zero"
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
  local plat arch jobs tmp mem
  # (the system's own kind, not the kernel's: a 32-bit Raspberry Pi OS can run a 64-bit kernel). A Pi 5
  # runs the Pi 4's build: the same OpenGL ES 3 drawing, without the extras it'd add
  case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
    arm64|aarch64) arch=aarch64; plat=rpi4_64 ;;
    armhf|armv7l) arch=arm; plat=rpi4 ;;
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
    && working "Building" "$tmp/build.log" make -C "$tmp" platform="$plat" ARCH="$arch" -j"$jobs" \
    || { tail -n 20 "$tmp/build.log"; rm -rf "$tmp"; return 1; }
  install -d "$CORES" && install -m 644 "$tmp/mupen64plus_next_libretro.so" "$CORES/" || { rm -rf "$tmp"; return 1; }
  echo "$MUPEN64PLUS" > "$CORES/mupen64plus_next.version"
  rm -rf "$tmp"
}
case "$MODEL" in
  *"Pi 4"*|*"Pi 5"*|*"Compute Module 4"*|*"Compute Module 5"*)
    if [ "$(cat "$CORES/mupen64plus_next.version" 2>/dev/null)" = "$MUPEN64PLUS" ] \
        && [ -f "$CORES/mupen64plus_next_libretro.so" ]; then
      echo "The N64 emulator (Mupen64Plus-Next) is built already."
    else
      step "Building the N64 emulator (Mupen64Plus-Next): about 20 minutes on a Pi 4, less on a Pi 5"
      build_mupen64plus || echo "(Couldn't build Mupen64Plus-Next: N64 games won't start.)"
    fi ;;
  *) echo "(N64 games need a Pi 4 or 5: no N64 emulator on this one.)" ;;
esac

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
case "$MODEL" in
  *"Pi 4"*|*"Pi 5"*|*"Compute Module 4"*|*"Compute Module 5"*)
    if [ "$(cat "$CORES/ppsspp.version" 2>/dev/null)" = "$PPSSPP_BUILT" ] && [ -f "$CORES/ppsspp_libretro.so" ] \
        && [ -f "$CORES/PPSSPP/compat.ini" ]; then
      echo "The PSP emulator (PPSSPP) is built already."
    else
      step "Building the PSP emulator (PPSSPP): about an hour on a Pi 4, 20 minutes on a Pi 5"
      build_ppsspp || echo "(Couldn't build PPSSPP: PSP games won't start.)"
    fi ;;
  *) echo "(PSP games need a Pi 4 or 5: no PSP emulator on this one.)" ;;
esac

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
  local jobs mem tmp
  jobs=$(nproc 2>/dev/null || echo 1)
  mem=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
  if [ "$mem" -lt 1500 ]; then jobs=1; elif [ "$mem" -lt 3000 ] && [ "$jobs" -gt 2 ]; then jobs=2; fi
  apt-get install -y build-essential git libgles-dev || return 1
  tmp="$(mktemp -d /var/tmp/melonds-XXXXXX)" || return 1
  BUILDING="$tmp"
  working "Downloading" "$tmp/build.log" melonds_source "$tmp" \
    && working "Building" "$tmp/build.log" make -C "$tmp/src" platform=rpi4_64 -j"$jobs" \
    || { tail -n 20 "$tmp/build.log"; rm -rf "$tmp"; return 1; }
  install -d "$CORES" && install -m 644 "$tmp/src/melonds_libretro.so" "$CORES/" || { rm -rf "$tmp"; return 1; }
  echo "$MELONDS" > "$CORES/melonds.version"
  rm -rf "$tmp"
}
case "$MODEL" in
  *"Pi 4"*|*"Pi 5"*|*"Compute Module 4"*|*"Compute Module 5"*)
    case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
      arm64|aarch64)
        if [ "$(cat "$CORES/melonds.version" 2>/dev/null)" = "$MELONDS" ] && [ -f "$CORES/melonds_libretro.so" ]; then
          echo "The DS emulator (melonDS) is built already."
        else
          step "Building the DS emulator (melonDS): about 10 minutes on a Pi 4, less on a Pi 5"
          build_melonds || echo "(Couldn't build melonDS: DS games won't start.)"
        fi ;;
      *) echo "(DS games need the 64-bit Raspberry Pi OS: no DS emulator on this one.)" ;;
    esac ;;
  *) echo "(DS games need a Pi 4 or 5: no DS emulator on this one.)" ;;
esac

step "Installing LibreOffice (Word, Excel and PowerPoint files with their real layout; about 400 MB)"
apt-get install -y --no-install-recommends libreoffice-core libreoffice-writer \
  libreoffice-calc libreoffice-impress || echo "(Couldn't install LibreOffice: documents open as plain text.)"

# --------------------------------------------------------------------------
if [ "$GPI" = yes ]; then
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
  sed -i -E 's|^([^#]*RetroFlag/SafeShutdown\.py.*)$|# \1   # (Pitato looks after the power switch)|' /etc/rc.local
  echo "Turned off RetroFlag's SafeShutdown.py in /etc/rc.local: Pitato looks after the power switch."
fi

else
  if grep -q '^# >>> gpi-case setup >>>' "$CONFIG"; then
    step "Taking the GPi Case settings out of $CONFIG (backup saved next to it)"
    cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d-%H%M%S)"
    sed -i '/^# >>> gpi-case setup >>>/,/^# <<< gpi-case setup <<</d' "$CONFIG"
    # HDMI screens need KMS, which the case's settings had turned off
    sed -i -E 's/^#dtoverlay=vc4-kms-v3d/dtoverlay=vc4-kms-v3d/' "$CONFIG"
  fi
  CMDLINE="$BOOT/cmdline.txt"
  PICKED="$(grep -oE 'video=HDMI-A-1:[0-9]+x[0-9]+' "$CMDLINE" 2>/dev/null | head -n 1 | sed 's/.*://')"
  if [ "$SLOW" = yes ] && [ -n "$PICKED" ] && [ "$PICKED" != 1280x720 ]; then
    echo "The TV picture stays at $PICKED (Settings > Resolution changes it)."
  elif [ "$SLOW" = yes ] && [ -f "$CMDLINE" ] && [ "$UPDATE" != yes ]; then   # (an update: left as it is)
    echo
    echo "This Pi plays video more smoothly on a TV set to 720p than at 1080p."
    read -r -p "Set the TV picture to 720p? [Y/n] " ans
    if [[ ! "$ans" =~ ^[Nn] ]]; then
      cp "$CMDLINE" "$CMDLINE.bak-$(date +%Y%m%d-%H%M%S)"
      sed -i -E 's/ *video=HDMI-A-1:[^ ]*//; 1 s/$/ video=HDMI-A-1:1280x720@60/' "$CMDLINE"
    elif grep -q 'video=HDMI-A-1:1280x720@60' "$CMDLINE"; then
      sed -i -E 's/ *video=HDMI-A-1:1280x720@60//' "$CMDLINE"      # this script's 720p, undone
    fi
  fi
fi

# --------------------------------------------------------------------------
step "Installing the controller and media script"
install -m 755 "$HERE/pitato.py" /usr/local/bin/pitato.py        # (it starts the rest: the pitato folder)
rm -rf /usr/local/share/pitato/pitato                          # (a fresh copy: no old files left in it)
install -d /usr/local/share/pitato/pitato/screens
install -m 644 "$HERE"/pitato/*.py /usr/local/share/pitato/pitato/
install -m 644 "$HERE"/pitato/screens/*.py /usr/local/share/pitato/pitato/screens/
python3 -m compileall -q /usr/local/share/pitato/pitato > /dev/null || true   # (quicker to start)

grep -qx uinput /etc/modules || echo uinput >> /etc/modules
modprobe uinput || true

cat > /etc/systemd/system/pitato.service <<EOF
[Unit]
Description=Pitato: controller buttons as keys, and media mode
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
  systemctl disable gpi-keys 2>/dev/null || true   # (Pitato by the name it had before: it goes at the end)
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
step "Installing the web page (port 5432)"
install -d /usr/local/share/pitato/templates
install -m 644 "$HERE/pitato/webui.py" /usr/local/share/pitato/
install -m 644 "$HERE/pitato/coder_hooks.py" /usr/local/share/pitato/    # (the page hands it to Claude Code's computer)
install -m 644 "$HERE/templates/index.html" /usr/local/share/pitato/templates/
install -d /usr/local/share/pitato/static/fonts    # the typefaces: the page's, and the home screen's (without them: the system's)
for f in "$HERE"/static/fonts/*; do
  if [ -f "$f" ]; then install -m 644 "$f" /usr/local/share/pitato/static/fonts/; fi
done
rm -rf /usr/local/share/pitato/index.html /usr/local/share/pitato/fonts    # (where they were before)

cat > /etc/systemd/system/pitato-web.service <<WEBUI
[Unit]
Description=Pitato web page: the screen and your files (port 5432)
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
if [ -f /etc/systemd/system/gpi-webui.service ]; then  # (the web page by the name it had before Pitato's)
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
case "$MODEL" in *"Pi 4"*|*"Pi 5"*|*"Compute Module 4"*|*"Compute Module 5"*) GAME_FOLDERS="$GAME_FOLDERS n64 psp nds" ;; esac
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
step "Camera tab (optional)"
if grep -qE '^\s*(url|ip|camera)\s*=' "$STATIC/camera.txt" 2>/dev/null \
   && ! grep -q 'Tail Air' "$STATIC/camera.txt"; then
  echo "Keeping your existing $STATIC/camera.txt"
elif [ "$UPDATE" = yes ]; then
  echo "No cameras yet: add them on the Camera tab."
else
  echo "The Camera tab shows the cameras on your other Pis (set one up with  sudo bash setup.sh --camera )"
  echo "or any camera link. You can also add them later on the Camera tab."
  read -r -p "A camera's address, e.g. 192.168.1.50 (blank to skip): " cam_url
  if [ -n "$cam_url" ]; then
    cat > "$STATIC/camera.txt" <<CAM
# Cameras for the Camera tab, one per line:   camera = address   (a name after it if you like)
# A Pi running Pitato's camera server (sudo bash setup.sh --camera),
# or any MJPEG or JPEG camera link.
camera = $cam_url
CAM
    chown "$USER_NAME:$USER_NAME" "$STATIC/camera.txt"
  fi
fi

# --------------------------------------------------------------------------
step "Finance tab"
FIN_HEAD="# Finance: stocks by their tickers, as on finance.yahoo.com (AAPL, AMZN, TSLA), and coins by their
# CoinGecko ids, as in coingecko.com/en/coins/bitcoin. Y on the Finance tab looks them up and adds
# them, or removes them."
if [ -f "$STATIC/finance.txt" ]; then
  echo "Keeping your existing $STATIC/finance.txt"
elif [ -f "$STATIC/crypto.txt" ]; then                   # (the Crypto tab's, from before it was Finance)
  echo "The Crypto tab is Finance now, with stocks too: your coins have moved from crypto.txt to finance.txt."
  { echo "$FIN_HEAD"
    grep -qiE '^[[:space:]]*stocks[[:space:]]*=' "$STATIC/crypto.txt" || echo "stocks = AAPL, AMZN, TSLA"
    grep -vE '^[[:space:]]*#' "$STATIC/crypto.txt" || true
  } > "$STATIC/finance.txt"
  chown "$USER_NAME:$USER_NAME" "$STATIC/finance.txt"
  rm -f "$STATIC/crypto.txt"
else
  echo "The Finance tab shows Apple, Amazon and Tesla (from Yahoo Finance), and Bitcoin, Ethereum and"
  echo "Dogecoin (from CoinGecko). Y on it looks up more to add."
  cat > "$STATIC/finance.txt" <<FINANCE
$FIN_HEAD
stocks = AAPL, AMZN, TSLA
coins = bitcoin, ethereum, dogecoin
FINANCE
  chown "$USER_NAME:$USER_NAME" "$STATIC/finance.txt"
fi

# --------------------------------------------------------------------------
step "TV Remote through Home Assistant (optional)"
if grep -qE '^\s*token\s*=\s*\S' "$STATIC/homeassistant.txt" 2>/dev/null; then
  echo "Keeping your existing $STATIC/homeassistant.txt"
elif [ "$UPDATE" = yes ]; then
  echo "No Home Assistant yet: run  sudo bash setup.sh  to add it."
else
  echo "TV > TV Remote and TV > Lights work through Home Assistant."
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
step "Bluetooth"
rfkill unblock bluetooth || true
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
  echo "(PipeWire or PulseAudio has Bluetooth's sound on this Pi: BlueALSA left out.)"
elif apt-get install -y bluez-alsa-utils libasound2-plugin-bluez && command -v bluealsa >/dev/null 2>&1; then
  install -d /etc/systemd/system/bluealsa.service.d
  cat > /etc/systemd/system/bluealsa.service.d/pitato.conf <<BLUEALSA
# Pitato (setup.sh): sound to Bluetooth headphones and speakers, the Pi as the player
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
# a camera server from before Pitato had its name: under the new one
if [ -f /etc/systemd/system/gpi-camera.service ] && [ -f "$HERE/pitato/camera.py" ]; then
  install_camera
fi

# Pitato by the name it had before (gpi-media): its service stops (it answered the questions above),
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
echo
if [ "$GPI" = yes ]; then
  echo "All set. Reboot to apply the screen and audio settings."
else
  echo "All set. Reboot to start."
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
