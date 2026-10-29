#!/usr/bin/env bash
# image/check.sh ROOT - before an image is let go, nothing of anyone's in it: no saved WiFi, SSH keys, passwords,
# sign-ins, Pietato settings of anyone's own, shell histories or git credentials. ROOT: its root filesystem, mounted,
# with its boot partition at ROOT/boot/firmware. It says what it finds, and fails if it finds anything.
# (image/build.sh runs it on each image it makes; it can look at any mounted image too.)
set -uo pipefail
R="${1:?Usage: bash image/check.sh MOUNTED_ROOT}"
R="${R%/}"
BOOT="$R/boot/firmware"
[ -d "$BOOT" ] || BOOT="$R/boot"
found=0
say() { echo "  found: $*"; found=1; }
shopt -s nullglob dotglob

# WiFi: saved networks, and what Raspberry Pi Imager leaves for the first start (WiFi, a user, a password, SSH)
for f in "$R"/etc/NetworkManager/system-connections/*; do say "a saved network (${f#"$R"})"; done
for f in "$R"/etc/wpa_supplicant/*.conf "$BOOT/wpa_supplicant.conf"; do
  if grep -qsE '^[[:space:]]*(network|psk|password|wep_key[0-9])[[:space:]]*=' "$f"; then say "WiFi settings (${f#"$R"})"; fi
done
for f in firstrun.sh userconf userconf.txt ssh ssh.txt user-data network-config custom.toml; do
  if [ -e "$BOOT/$f" ]; then say "a first-start setting in the boot partition ($f)"; fi
done

# SSH: this machine's own keys (each Pi makes its own), anyone's keys or hosts
for f in "$R"/etc/ssh/ssh_host_*; do say "an SSH host key (${f#"$R"})"; done
for d in "$R"/root/.ssh "$R"/home/*/.ssh; do
  for f in "$d"/*; do say "SSH files (${f#"$R"})"; done
done

# passwords: every account locked (no password, and not an empty one either)
if [ -f "$R/etc/shadow" ]; then
  while IFS=: read -r user pass _; do
    case "$pass" in
      '!'*|'*'*) ;;
      *) say "a password for $user" ;;
    esac
  done < "$R/etc/shadow"
else
  say "no /etc/shadow to look at"
fi

# Pietato: only its own starting settings files, and no sign-ins or saved state
for d in "$R"/home/*/pietato/static "$R"/home/*/pie-tato/static "$R"/home/*/pitato/static; do   # (pie-tato, pitato: its names before)
  for f in "$d"/*; do
    case "${f##*/}" in
      fonts|streams.txt|radio.txt|finance.txt) ;;
      *) say "a settings file (${f#"$R"})" ;;
    esac
  done
done
for f in "$R"/var/lib/pitato/*; do
  case "${f##*/}" in
    installed-commit) ;;
    *) say "Pietato's own saved things (${f#"$R"})" ;;
  esac
done
for d in "$R"/var/cache/pitato "$R"/root/.cache/pitato "$R"/home/*/.cache/pitato; do
  if [ -e "$d" ]; then say "Pietato's cache (${d#"$R"})"; fi
done

# histories and credentials
for d in "$R"/root "$R"/home/*; do
  for f in .bash_history .python_history .lesshst .viminfo .wget-hsts .git-credentials .netrc .gitconfig \
           .local/share/nano/search_history; do
    if [ -e "$d/$f" ]; then say "${d#"$R"}/$f"; fi
  done
done
for g in "$R"/home/*/pietato/.git/config "$R"/home/*/pie-tato/.git/config "$R"/home/*/pitato/.git/config; do
  if grep -qiE 'extraheader|authorization|x-access-token|://[^/[:space:]]*@' "$g"; then
    say "a credential in Pietato's git settings (${g#"$R"})"
  fi
done

# what's each Pi's own
if [ -s "$R/etc/machine-id" ]; then say "a machine-id (each Pi makes its own)"; fi

echo "  hostname: $(cat "$R/etc/hostname" 2> /dev/null)"
if [ "$found" -ne 0 ]; then
  echo "Not let go: something of someone's is in it (above)."
  exit 1
fi
echo "  nothing of anyone's in it"
