#!/usr/bin/env bash
# setup.sh - set up Raspberry Pi OS Lite (Bookworm) on any Raspberry Pi with a screen
#   - in a RetroFlag GPi Case 2W (Pi Zero 2 W): the case screen as the console (with
#     GPIO 18/19 left free for the speaker), the case speaker, and its power switch:
#     switching off shuts the Pi down safely (GPIO 26 and 27, as RetroFlag's own script)
#   - on any other Pi: the screen on HDMI as it is, and media mode at start-up
#   - game controller buttons as keys + media mode (the case buttons, or any USB or
#     Bluetooth controller), which opens on a home screen of app icons: TV (Plex,
#     cartoons, free movies, news, sports, streams, a TV remote through Home Assistant),
#     music, radio, photos (filters, delete), videos, weather, crypto prices and charts,
#     a file browser for PDFs/documents/text, cameras on your other Pis (PiE-ink, or
#     --camera below) with OBSBOT steering and pictures, a bot (Ollama on another
#     computer, a Piper voice on the Pi), system info, and settings (WiFi, background,
#     colours, location, sound, controller, bot...)  (gpi_keys.py, runs at boot)
#   - a web page for your phone or computer (webui.py, port 5432): see the screen, work
#     it with a remote, put cartoons, films, news or radio on it, and drag in files
#     that land in Music, Videos, Pictures or Documents
#   - optional: pair a Bluetooth keyboard or game controller
#
# Your settings files (radio.txt, bot.txt, crypto.txt...) go in this folder's static folder, so
# keep the folder where it is. Ones left in your home folder by an earlier version move there.
#
# Usage (from the repo folder):  sudo bash setup.sh
#   --gpi       it's in a GPi Case 2W (don't ask)
#   --no-gpi    it isn't (don't ask)
#   --camera    only share this Pi's USB camera on the network, for gpi-media's Camera tab on
#               another Pi (camera.py, port 5433); nothing else is installed
# Safe to run again: it replaces its own settings instead of adding duplicates.

set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo bash setup.sh"
  exit 1
fi

GPI=""
CAMERA=no
for arg in "$@"; do
  case "$arg" in
    --gpi) GPI=yes ;;
    --no-gpi) GPI=no ;;
    --camera) CAMERA=yes ;;
    *) echo "Unknown option: $arg (use --gpi, --no-gpi or --camera)"; exit 1 ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
STATIC="$HERE/static"                  # your settings files
case "$HERE" in
  *[\"\\]*) echo "Move the gpi-media folder somewhere without quotes or backslashes in its path."; exit 1 ;;
esac
if [ "$HERE" = "$USER_HOME" ] || [ "$HERE" = / ]; then
  echo "Keep gpi-media in a folder of its own (git clone makes one), not in $HERE itself."
  exit 1
fi
UNIT_STATIC="${STATIC//%/%%}"          # (as a systemd unit writes it)
if id "$USER_NAME" >/dev/null 2>&1 && command -v runuser >/dev/null \
   && ! runuser -u "$USER_NAME" -- test -r "$HERE" -a -x "$HERE"; then
  echo "$USER_NAME can't open $HERE, so the web page couldn't reach your settings in it."
  echo "Clone gpi-media into $USER_HOME and run setup.sh from there."
  exit 1
fi

step() { echo; echo "==> $*"; }

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
# --camera: this Pi only shares its USB camera, for gpi-media's Camera tab on another Pi
if [ "$CAMERA" = yes ]; then
  if [ ! -f "$HERE/camera.py" ]; then
    echo "camera.py isn't next to setup.sh. Run this from the gpi-media folder."
    exit 1
  fi
  step "Installing the camera server (this Pi's USB camera, port 5433)"
  apt-get update
  apt-get install -y ffmpeg v4l-utils python3
  install -d /usr/local/share/gpi-media
  install -m 644 "$HERE/camera.py" /usr/local/share/gpi-media/camera.py
  settings_folder camera-server.txt
  usermod -aG video "$USER_NAME" || true
  cat > /etc/systemd/system/gpi-camera.service <<CAMSVC
[Unit]
Description=gpi-media camera server: this Pi's USB camera on the network (port 5433)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
SupplementaryGroups=video
WorkingDirectory=$USER_HOME
Environment="GPI_MEDIA_STATIC=$UNIT_STATIC"
ExecStart=/usr/bin/python3 /usr/local/share/gpi-media/camera.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
CAMSVC
  systemctl daemon-reload
  systemctl enable gpi-camera
  systemctl restart gpi-camera || true
  echo
  echo "Done. On gpi-media's Camera tab, add this Pi:  $(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "It also shows up there by itself, under On your network."
  echo "To see the picture in a browser:  http://$(hostname).local:5433"
  exit 0
fi

for f in gpi_keys.py webui.py templates/index.html; do
  if [ ! -f "$HERE/$f" ]; then
    echo "$f isn't next to setup.sh. Run this from the gpi-media folder."
    exit 1
  fi
done


if [ -d /boot/firmware ]; then BOOT=/boot/firmware; else BOOT=/boot; fi
CONFIG="$BOOT/config.txt"

# --------------------------------------------------------------------------
# the GPi Case 2W needs its own screen and speaker settings; any other Pi uses HDMI
MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)"
SLOW=no         # Pi Zero, 1, 2 and 3: video on a big TV is smoother at 720p
case "$MODEL" in
  *Zero*|"Raspberry Pi 3"*|"Raspberry Pi 2"*|"Raspberry Pi Model"*|"Raspberry Pi Compute Module 3"*) SLOW=yes ;;
esac
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

# --------------------------------------------------------------------------
step "Installing packages"
apt-get update
apt-get install -y python3-evdev python3-pil python3-numpy fonts-dejavu-core \
  mplayer poppler-utils iw evtest device-tree-compiler python3-flask alsa-utils

echo
echo "Optional: LibreOffice shows Word/Excel/PowerPoint files with their real layout."
echo "It's a big download (~400 MB) and slow the first time you open a document."
echo "Without it, documents open as plain text."
read -r -p "Install LibreOffice? [y/N] " lo
if [[ "$lo" =~ ^[Yy] ]]; then
  apt-get install -y --no-install-recommends libreoffice-core libreoffice-writer \
    libreoffice-calc libreoffice-impress
fi

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
# GPi Case 2W speaker (PWM on GPIO 18/19)
dtparam=audio=on
dtoverlay=audremap,pins_18_19,enable_jack
# GPi Case 2W power switch: GPIO 27 keeps the case on while the Pi shuts down, and
# switching off (GPIO 26 goes low) shuts it down safely. The case's SAFE SHUTDOWN
# switch, behind the cartridge, goes to ON.
gpio=27=op,dh
dtoverlay=gpio-shutdown,gpio_pin=26,active_low=1,gpio_pull=up
# <<< gpi-case setup <<<
EOF

# RetroFlag's own safe-shutdown script would fight over the same pins
if [ -f /etc/rc.local ] && grep -qE '^[^#]*RetroFlag/SafeShutdown\.py' /etc/rc.local; then
  sed -i -E 's|^([^#]*RetroFlag/SafeShutdown\.py.*)$|# \1   # (gpi-media looks after the power switch)|' /etc/rc.local
  echo "Turned off RetroFlag's SafeShutdown.py in /etc/rc.local: gpi-media looks after the power switch."
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
  if [ "$SLOW" = yes ] && [ -f "$CMDLINE" ]; then
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
install -m 755 "$HERE/gpi_keys.py" /usr/local/bin/gpi_keys.py
if [ "$GPI" = no ] && [ ! -f /var/lib/gpi-keys/state.json ]; then
  # no case to hold: a Pi on a TV opens media mode at start-up (Settings > At start-up)
  install -d /var/lib/gpi-keys
  echo '{"settings": {"start": "Home screen"}}' > /var/lib/gpi-keys/state.json
fi

grep -qx uinput /etc/modules || echo uinput >> /etc/modules
modprobe uinput || true

cat > /etc/systemd/system/gpi-keys.service <<EOF
[Unit]
Description=gpi-media: controller buttons as keys, and media mode
After=multi-user.target

[Service]
Environment="GPI_MEDIA_STATIC=$UNIT_STATIC"
ExecStart=/usr/bin/python3 /usr/local/bin/gpi_keys.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable gpi-keys          # (started at the end: media mode would cover these questions)

# --------------------------------------------------------------------------
step "Installing the web page (port 5432)"
install -d /usr/local/share/gpi-media/templates
install -m 644 "$HERE/webui.py" /usr/local/share/gpi-media/
install -m 644 "$HERE/templates/index.html" /usr/local/share/gpi-media/templates/
install -d /usr/local/share/gpi-media/static/fonts    # its typeface (without it: the system's)
for f in "$HERE"/static/fonts/*; do
  if [ -f "$f" ]; then install -m 644 "$f" /usr/local/share/gpi-media/static/fonts/; fi
done
rm -rf /usr/local/share/gpi-media/index.html /usr/local/share/gpi-media/fonts    # (where they were before)

cat > /etc/systemd/system/gpi-webui.service <<WEBUI
[Unit]
Description=gpi-media web page: the screen and your files (port 5432)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$USER_HOME
Environment="GPI_MEDIA_STATIC=$UNIT_STATIC"
ExecStart=/usr/bin/python3 /usr/local/share/gpi-media/webui.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
WEBUI
systemctl daemon-reload
systemctl enable gpi-webui

# settings files an earlier version kept in your home folder go in the static folder now: with the
# web page stopped meanwhile, as until it restarts it would look for its password in the old place
systemctl stop gpi-webui 2>/dev/null || true
settings_folder radio.txt streams.txt streams.m3u crypto.txt camera.txt bot.txt \
  homeassistant.txt webui.txt plex.txt
if [ ! -e "$STATIC/bot.txt" ]; then
  settings_folder friend.txt                        # the bot's settings, by their earlier name
fi
systemctl restart gpi-webui || true

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
  rm -rf /var/cache/gpi-media /var/lib/gpi-keys/youtube.json
  if id gpi-media >/dev/null 2>&1; then userdel gpi-media || true; fi
fi

# --------------------------------------------------------------------------
step "Making $USER_HOME/Videos, Music, Pictures and Documents, and your settings in $STATIC"
mkdir -p "$USER_HOME/Videos" "$USER_HOME/Music" "$USER_HOME/Pictures" "$USER_HOME/Documents"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/Videos" "$USER_HOME/Music" "$USER_HOME/Pictures" \
  "$USER_HOME/Documents"
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
else
  echo "The Camera tab shows the cameras on your other Pis: one running PiE-ink, or one set up"
  echo "with  sudo bash setup.sh --camera . You can also add them later on the Camera tab."
  read -r -p "A camera's address, e.g. 192.168.1.50 (blank to skip): " cam_url
  if [ -n "$cam_url" ]; then
    cat > "$STATIC/camera.txt" <<CAM
# Cameras for the Camera tab, one per line:   camera = address   (a name after it if you like)
# A Pi running PiE-ink or gpi-media's camera server (sudo bash setup.sh --camera),
# or any MJPEG or JPEG camera link.
camera = $cam_url
CAM
    chown "$USER_NAME:$USER_NAME" "$STATIC/camera.txt"
  fi
fi

# --------------------------------------------------------------------------
step "Crypto tab"
if [ -f "$STATIC/crypto.txt" ]; then
  echo "Keeping your existing $STATIC/crypto.txt"
else
  echo "The Crypto tab shows coin prices and charts from CoinGecko."
  read -r -p "Coins (CoinGecko ids, Enter for bitcoin, ethereum, dogecoin): " coins
  cat > "$STATIC/crypto.txt" <<CRYPTO
# Crypto tab. Coins are CoinGecko ids (the name in the coin's coingecko.com address).
coins = ${coins:-bitcoin, ethereum, dogecoin}
CRYPTO
  chown "$USER_NAME:$USER_NAME" "$STATIC/crypto.txt"
fi

# --------------------------------------------------------------------------
step "TV Remote through Home Assistant (optional)"
if grep -qE '^\s*token\s*=\s*\S' "$STATIC/homeassistant.txt" 2>/dev/null; then
  echo "Keeping your existing $STATIC/homeassistant.txt"
else
  echo "TV > TV Remote controls your TV through Home Assistant."
  echo "Make a token in Home Assistant: your profile > Security > Long-lived access tokens."
  read -r -p "Home Assistant address, e.g. homeassistant.local:8123 (blank to skip): " ha_url
  if [ -n "$ha_url" ]; then
    read -r -s -p "Long-lived access token (hidden as you paste): " ha_token
    echo
    read -r -p "TV entity, e.g. media_player.living_room_tv (Enter to find it): " ha_tv
    ( umask 077
      cat > "$STATIC/homeassistant.txt" <<HA
# TV Remote: your Home Assistant and a long-lived access token. Keep this file private.
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

read -r -p "Pair a Bluetooth keyboard or game controller now? [y/N] " ans
if [[ "$ans" =~ ^[Yy] ]]; then
  echo "Put it in pairing mode: a keyboard on a free profile, a controller by holding its"
  echo "pairing button (Share + PS on a PlayStation pad, the pair button on Xbox and 8BitDo)."
  read -r -p "Press Enter when it's ready... " _
  bluetoothctl power on >/dev/null
  bluetoothctl pairable on >/dev/null
  echo "Scanning for 20 seconds..."
  bluetoothctl --timeout 20 scan on >/dev/null 2>&1 || true
  echo
  bluetoothctl devices
  echo
  read -r -p "Type its address (XX:XX:XX:XX:XX:XX): " addr
  if [ -n "$addr" ]; then
    bluetoothctl remove "$addr" >/dev/null 2>&1 || true
    bluetoothctl --timeout 20 scan on >/dev/null 2>&1 &
    sleep 5
    bluetoothctl pair "$addr" || echo "(pair reported an error - checking connection anyway)"
    bluetoothctl trust "$addr"
    bluetoothctl connect "$addr" || true
    wait || true
    bluetoothctl info "$addr" | grep -E "Name|Paired|Trusted|Connected"
  fi
fi

# --------------------------------------------------------------------------
echo
if [ "$GPI" = yes ]; then
  echo "All set. Reboot to apply the screen and audio settings."
else
  echo "All set. Reboot to start media mode."
fi
echo "On your phone or computer, open  http://$(hostname).local:5432"
echo "to see the screen, work it with a remote, and add files."
echo "Your settings files are in $STATIC"
read -r -p "Reboot now? [Y/n] " ans
if [[ ! "$ans" =~ ^[Nn] ]]; then
  reboot
else
  systemctl restart gpi-keys || true
fi
