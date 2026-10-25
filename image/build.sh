#!/usr/bin/env bash
# image/build.sh - Pitato's SD card images, made from a fresh Raspberry Pi OS Lite (Bookworm, 64-bit) that's never
# started while they're made. In them: Raspberry Pi OS, Pitato and its emulators, and nothing of anyone's (no WiFi,
# sign-ins, keys or passwords: image/check.sh looks before each one's let go). Two of them: one for the GPi Case 2W,
# one for a TV or monitor on HDMI. GitHub makes them for each release (.github/workflows/image.yml); on 64-bit ARM
# Linux (a Pi 4 or 5 with the 64-bit Raspberry Pi OS, say) this makes them too:
#   sudo bash image/build.sh OUT_FOLDER [NAME]
# NAME: what they're called after "pitato-" (the release's tag); the date when left out. Pitato goes in as git clone
# gets it (so Update software works): PITATO_REPO (owner/name) and PITATO_COMMIT say which (GitHub's own, there).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:?Usage: sudo bash image/build.sh OUT_FOLDER [NAME]}"
NAME="${2:-$(date +%Y-%m-%d)}"
REPO="${PITATO_REPO:-${GITHUB_REPOSITORY:-frogCaller/pitato}}"
COMMIT="${PITATO_COMMIT:-${GITHUB_SHA:-}}"
OS_LIST="https://downloads.raspberrypi.com/os_list_imagingutility_v4.json"   # (Raspberry Pi Imager's own list)
GROW=4G            # room to put Pitato in, taken back off at the end (Raspberry Pi OS grows it to fill the card when it
                   # first starts)
# (for its tests, on a computer that isn't 64-bit ARM: PITATO_ANY_ARCH=1, PITATO_BASE_IMG a base image already here,
# and PITATO_CLONE_FROM a folder to clone Pitato from)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run it as root:  sudo bash image/build.sh OUT_FOLDER"
  exit 1
fi
case "$(uname -m)" in
  aarch64|arm64) ;;
  *) if [ "${PITATO_ANY_ARCH:-}" != 1 ]; then
       echo "This makes 64-bit ARM images: run it on 64-bit ARM Linux (GitHub's ubuntu-24.04-arm, or a Pi 4 or 5)."
       exit 1
     fi ;;
esac
for c in curl xz losetup sfdisk e2fsck resize2fs dumpe2fs git python3 chroot sha256sum truncate; do
  command -v "$c" > /dev/null || { echo "It needs $c."; exit 1; }
done

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
best="" most=0                         # (to work in: wherever has the most room)
for d in "${PITATO_WORK:-}" /mnt "$OUT" /var/tmp; do
  [ -n "$d" ] && [ -d "$d" ] && [ -w "$d" ] || continue
  free=$(df -Pk "$d" | awk 'NR == 2 {print $4}')
  if [ "$free" -gt "$most" ]; then most=$free; best=$d; fi
done
WORK="$(mktemp -d "$best/pitato-image-XXXXXX")"
IMG="$WORK/pitato.img"
ROOT="$WORK/root"
echo "Working in $WORK ($((most / 1048576)) GB free there)"
if [ "$most" -lt $((9 * 1048576)) ]; then echo "(Under 9 GB free: it may run out of room.)"; fi

LOOPS=()
unmount_all() {    # everything mounted in ROOT (the deepest first), and the image's partitions let go
  local m
  for m in $(awk -v r="$ROOT" '$2 == r || index($2, r "/") == 1 {print $2}' /proc/mounts | sort -r); do
    umount "$m" 2> /dev/null || umount -l "$m" 2> /dev/null || true
  done
  for m in "${LOOPS[@]}"; do losetup -d "$m" 2> /dev/null || true; done
  LOOPS=()
}
cleanup() {
  set +e
  unmount_all
  rm -rf "$WORK"
}
trap cleanup EXIT

part() {           # part N: partition N of the image, "start size" (512-byte sectors)
  sfdisk -J "$IMG" | python3 -c 'import json, sys
p = json.load(sys.stdin)["partitiontable"]["partitions"][int(sys.argv[1]) - 1]
print(p["start"], p["size"])' "$1"
}
attach() {         # attach N VAR: a loop device for partition N, in VAR (the caller's: these names are its own)
  local _start _size _dev
  read -r _start _size < <(part "$1")
  _dev=$(losetup -f --show -o $((_start * 512)) --sizelimit $((_size * 512)) "$IMG")
  LOOPS+=("$_dev")
  printf -v "$2" '%s' "$_dev"
}
fsck_ok() {        # e2fsck: put right, or nothing to put right
  local rc=0
  e2fsck -pf "$1" > /dev/null || rc=$?
  [ "$rc" -le 1 ] || { echo "e2fsck found what it couldn't put right ($rc)"; exit 1; }
}
grow() {           # grow SIZE: the image SIZE bigger, its root filesystem with it
  local dev
  truncate -s +"$1" "$IMG"
  echo ", +" | sfdisk --no-reread -q -N 2 "$IMG" > /dev/null
  attach 2 dev
  fsck_ok "$dev"
  resize2fs "$dev" > /dev/null 2>&1
  unmount_all
}
mount_image() {    # its root at ROOT and boot at ROOT/boot/firmware, with what a chroot needs
  local rootdev bootdev
  attach 2 rootdev
  attach 1 bootdev
  mkdir -p "$ROOT"
  mount "$rootdev" "$ROOT"
  mount "$bootdev" "$ROOT/boot/firmware"
  mount --bind /dev "$ROOT/dev"
  mount --bind /dev/pts "$ROOT/dev/pts"
  mount -t proc proc "$ROOT/proc"
  mount -t sysfs sysfs "$ROOT/sys"
  mount -t tmpfs tmpfs "$ROOT/run"
  mount -t tmpfs tmpfs "$ROOT/tmp"
  mv "$ROOT/etc/resolv.conf" "$ROOT/etc/resolv.conf.pitato"     # (this computer's, to reach the internet meanwhile)
  cp -L /etc/resolv.conf "$ROOT/etc/resolv.conf"
  printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"  # (nothing installed starts up meanwhile)
  chmod 755 "$ROOT/usr/sbin/policy-rc.d"
  # (and systemctl, meanwhile: what's set to start goes to the real one; nothing starts or stops, as nothing's running)
  cat > "$ROOT/usr/local/sbin/systemctl" <<'SHIM'
#!/bin/sh
# image/build.sh's, while it makes the image: nothing's running in it to start, stop or reload
for a in "$@"; do
  case "$a" in
    -*) ;;
    daemon-reload|daemon-reexec|start|stop|restart|reload|try-restart|reload-or-restart|kill|reset-failed) exit 0 ;;
    is-active|is-failed) exit 3 ;;
    *) break ;;
  esac
done
for a do shift; [ "$a" = --now ] || set -- "$@" "$a"; done
exec /usr/bin/systemctl "$@"
SHIM
  chmod 755 "$ROOT/usr/local/sbin/systemctl"
}
in_root() {        # a command in the image, as root
  chroot "$ROOT" /usr/bin/env -i HOME=/root TERM=dumb LANG=C.UTF-8 LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "$@"
}

# --------------------------------------------------------------------------
fetch_base() {     # Raspberry Pi OS Lite (Bookworm, 64-bit), as Raspberry Pi Imager lists it, checked
  if [ -n "${PITATO_BASE_IMG:-}" ]; then
    cp --sparse=always "$PITATO_BASE_IMG" "$IMG"
    return
  fi
  local url="${PITATO_BASE_URL:-}" sha="${PITATO_BASE_SHA256:-}"
  if [ -z "$url" ]; then
    read -r url sha < <(curl -fsSL --retry 3 "$OS_LIST" | python3 -c 'import json, sys
def walk(items):
    for it in items:
        yield it
        yield from walk(it.get("subitems") or [])
for it in walk(json.load(sys.stdin).get("os_list") or []):
    u = it.get("url") or ""
    if "raspios_oldstable_lite_arm64" in u and "bookworm" in u and it.get("extract_sha256"):
        print(u, it["extract_sha256"])
        break') || true
  fi
  if [ -z "$url" ] || [ -z "$sha" ]; then
    echo "Raspberry Pi OS Lite (Bookworm, 64-bit) isn't in Raspberry Pi Imager's list (PITATO_BASE_URL and"
    echo "PITATO_BASE_SHA256 can say where it is)."
    exit 1
  fi
  echo "Raspberry Pi OS: $url"
  curl -fL --retry 3 -sS -o "$WORK/base.img.xz" "$url"
  xz -dc "$WORK/base.img.xz" > "$IMG"
  rm -f "$WORK/base.img.xz"
  echo "$sha  $IMG" | sha256sum -c --quiet - || { echo "That isn't the Raspberry Pi OS Raspberry Pi lists."; exit 1; }
}

put_in_pitato() { # Pitato's folder in the first user's home, as git clone makes it, theirs
  local dir gid
  IMG_USER=$(awk -F: '$3 == 1000 {print $1; exit}' "$ROOT/etc/passwd")
  IMG_HOME=$(awk -F: '$3 == 1000 {print $6; exit}' "$ROOT/etc/passwd")
  gid=$(awk -F: '$3 == 1000 {print $4; exit}' "$ROOT/etc/passwd")
  if [ -z "$IMG_USER" ] || [ ! -d "$ROOT$IMG_HOME" ]; then
    echo "Raspberry Pi OS has no first user here (1000, with a home)."
    exit 1
  fi
  dir="$ROOT$IMG_HOME/pitato"
  rm -rf "$dir"
  git clone -q --depth 1 --branch main "${PITATO_CLONE_FROM:-https://github.com/$REPO.git}" "$dir"
  if [ -n "$COMMIT" ] && [ "$(git -C "$dir" rev-parse HEAD)" != "$COMMIT" ]; then
    git -C "$dir" fetch -q --depth 1 origin "$COMMIT"
    git -C "$dir" reset -q --hard FETCH_HEAD
  fi
  git -C "$dir" remote set-url origin "https://github.com/$REPO.git"
  echo "Pitato: $REPO at $(git -C "$dir" rev-parse --short HEAD)"
  chown -R "1000:$gid" "$dir"
}

image_settings() { # what an image has that a Pi set up by hand doesn't
  # no questions the first time it starts (the GPi Case has no keyboard to answer them): the first user signs in
  # by itself. Raspberry Pi Imager can still name it, give it a password, and add WiFi and SSH as it writes the card
  in_root systemctl disable userconfig.service > /dev/null 2>&1 || true
  in_root systemctl enable getty@tty1.service > /dev/null 2>&1
  rm -f "$ROOT/etc/ssh/sshd_config.d/rename_user.conf"     # (SSH's "until a valid user has been set up": it is)
  in_root systemctl enable regenerate_ssh_host_keys.service > /dev/null 2>&1 || true   # (each Pi its own)
  echo pitato > "$ROOT/etc/hostname"
  sed -i -E 's/^(127\.0\.1\.1[[:space:]]+).*/\1pitato/' "$ROOT/etc/hosts"
  # no passwords that work (Imager sets yours): the accounts locked, as Raspberry Pi OS's are
  in_root usermod -L "$IMG_USER" > /dev/null 2>&1 || true
  in_root usermod -L root > /dev/null 2>&1 || true
  # WiFi on (Raspberry Pi OS keeps it off till a country's picked; till then, the rules that hold everywhere), so
  # Pitato's Settings can join a network
  for f in "$ROOT"/var/lib/systemd/rfkill/*:wlan; do
    if [ -e "$f" ]; then echo 0 > "$f"; fi
  done
  if [ -f "$ROOT/var/lib/NetworkManager/NetworkManager.state" ]; then
    sed -i 's/^WirelessEnabled=.*/WirelessEnabled=true/' "$ROOT/var/lib/NetworkManager/NetworkManager.state"
  fi
  # Pitato's services follow its folder (Imager can rename the user, and its home), and the first start's own bits
  install -D -m 755 "$HERE/pitato-user" "$ROOT/etc/systemd/system-generators/pitato-user"
  install -D -m 755 "$HERE/pitato-firstboot" "$ROOT/usr/local/share/pitato/image-firstboot"
  cat > "$ROOT/etc/systemd/system/pitato-firstboot.service" <<'UNIT'
[Unit]
Description=Pitato: the first start from its SD card image
ConditionPathExists=!/var/lib/pitato/image-firstboot-done
Before=pitato.service pitato-web.service

[Service]
Type=oneshot
ExecStart=/usr/local/share/pitato/image-firstboot

[Install]
WantedBy=multi-user.target
UNIT
  in_root systemctl enable pitato-firstboot.service > /dev/null 2>&1
}

tidy() {           # nothing left from making it
  in_root apt-get clean
  rm -rf "$ROOT"/var/lib/apt/lists/* "$ROOT"/var/tmp/* "$ROOT"/var/cache/apt/*.bin
  find "$ROOT/var/log" -type f ! -path '*/journal/*' -exec truncate -s 0 {} +
  rm -f "$ROOT"/etc/ssh/ssh_host_* "$ROOT"/boot/firmware/*.bak-*
  : > "$ROOT/etc/machine-id"                              # (each Pi makes its own)
  rm -rf "$ROOT"/root/.cache "$ROOT"/home/*/.cache
  rm -f "$ROOT"/root/.bash_history "$ROOT"/root/.python_history "$ROOT"/root/.wget-hsts "$ROOT"/root/.lesshst
  rm -f "$ROOT/usr/sbin/policy-rc.d" "$ROOT/usr/local/sbin/systemctl"
  mv -f "$ROOT/etc/resolv.conf.pitato" "$ROOT/etc/resolv.conf"
}

shrink() {         # the root filesystem as small as resize2fs makes it (it leaves some room), what's free in it zeros
  local dev bs blocks start want                         # (they pack away to nothing), and the image cut to it
  attach 2 dev
  fsck_ok "$dev"
  resize2fs -M "$dev" > /dev/null 2>&1
  fsck_ok "$dev"
  mkdir -p "$ROOT"
  mount "$dev" "$ROOT"
  dd if=/dev/zero of="$ROOT/.zeros" bs=4M status=none 2> /dev/null || true
  rm -f "$ROOT/.zeros"
  sync
  umount "$ROOT"
  bs=$(dumpe2fs -h "$dev" 2> /dev/null | awk -F: '/^Block size/ {print $2 + 0}')
  blocks=$(dumpe2fs -h "$dev" 2> /dev/null | awk -F: '/^Block count/ {print $2 + 0}')
  unmount_all
  read -r start _ < <(part 2)
  want=$(( (blocks * bs + 511) / 512 ))
  echo "$start,$want" | sfdisk --no-reread -q -N 2 "$IMG" > /dev/null
  truncate -s $(( (start + want) * 512 )) "$IMG"
}

make_one() {       # make_one --no-gpi|--gpi KIND: Pitato set up for that screen, checked, out as OUT/pitato-NAME-KIND
  local file="pitato-$NAME-$2.img.xz"
  echo
  echo "==> $file"
  mount_image
  if [ "$1" = --no-gpi ]; then put_in_pitato; fi
  IMG_USER=$(awk -F: '$3 == 1000 {print $1; exit}' "$ROOT/etc/passwd")
  IMG_HOME=$(awk -F: '$3 == 1000 {print $6; exit}' "$ROOT/etc/passwd")
  in_root env SUDO_USER="$IMG_USER" bash "$IMG_HOME/pitato/setup.sh" --image "$1" < /dev/null
  if [ "$1" = --no-gpi ]; then image_settings; fi
  tidy
  bash "$HERE/check.sh" "$ROOT"
  sync
  unmount_all
  shrink
  echo "Compressing ($(( $(stat -c %s "$IMG") / 1048576 )) MB)"
  xz -T0 -6 -c "$IMG" > "$OUT/$file"
  (cd "$OUT" && sha256sum "$file" > "$file.sha256")
  echo "$OUT/$file: $(( $(stat -c %s "$OUT/$file") / 1048576 )) MB"
}

# --------------------------------------------------------------------------
fetch_base
grow "$GROW"
make_one --no-gpi hdmi
grow 1G                                                    # (room for the package lists again)
make_one --gpi gpi-case-2w
echo
echo "Done: $(cd "$OUT" && ls pitato-"$NAME"-*.img.xz | tr '\n' ' ')"
