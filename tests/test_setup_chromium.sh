#!/bin/bash
# setup.sh's part for Chromium, on its own: a Pi 4 (BIG) not in a GPi Case 2W puts in cage, Xwayland, wlr-randr, the
# fonts, libpam-systemd (its session's; a small Debian may not have it) and Chromium (chromium, or else
# chromium-browser), and writes its PAM service; a GPi Case 2W, or a slower Pi,
# doesn't; nothing to install: it says so and carries on. On Ubuntu (a PC): chromium-browser at once (its snap), never
# a chromium package it hasn't got. (Raspberry Pi OS's os-release, Debian's, unless it's Ubuntu's: this machine's.)
SP="${PIETATO_TEST_WORK:?run it with tests/run.py}"
ROOT="${PITATO_ROOT:?}"
D=$SP/setupchrome
part=$(awk '/^# Chromium, from Web.s first page/{on=1} /^step "Installing LibreOffice/{on=0} on' "$ROOT/setup.sh" \
  | sed "s#/etc/pam.d/pietato-chromium#\$PAMDIR/pietato-chromium#")
fails=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi; }
printf 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nNAME="Debian GNU/Linux"\nVERSION_ID="12"\nID=debian\n' > "$D/debian-os-release"
run() {   # BIG CASE APT_MISSING [OS_RELEASE]
  rm -rf "$D/pam" "$D/log"; mkdir -p "$D/pam"
  out=$(set -e; PATH="$D/bin:$PATH" LOG="$D/log" PAMDIR="$D/pam" BIG="$1" CASE="$2" APT_MISSING="$3" \
        PITATO_OS_RELEASE="${4:-$D/debian-os-release}" bash -c "set -e; step() { echo \"==> \$*\"; }; $part; echo DONE" 2>&1)
}
run yes "" ""
check "a Pi 4 (or a PC with Debian, its os-release the same): cage, Xwayland, wlr-randr, the fonts and libpam-systemd, then chromium" \
  '[ "$(cat $D/log)" = "apt-get install -y cage xwayland wlr-randr fonts-liberation fonts-noto-color-emoji libpam-systemd
apt-get install -y chromium" ]'
check "...its PAM service: your session, with pam_systemd, no password asked" \
  'grep -q "^session   required  pam_systemd.so" $D/pam/pietato-chromium && ! grep -q "pam_deny" $D/pam/pietato-chromium'
check "...and on to the rest (set -e kept)" '[[ "$out" == *DONE ]]'
run yes 2 "chromium"
check "a GPi Case 2 (a CM4), no package called chromium: chromium-browser" \
  'tail -n 1 $D/log | grep -qx "apt-get install -y chromium-browser" && [ -f $D/pam/pietato-chromium ]'
run yes "" "cage"
check "cage not to be had: it says so, no PAM service, on to the rest" \
  '[[ "$out" == *"Couldn'"'"'t install Chromium"* ]] && [ ! -f $D/pam/pietato-chromium ] && [[ "$out" == *DONE ]]'
run yes 2w ""
check "a GPi Case 2W: nothing" '[ ! -s $D/log ] && [ ! -f $D/pam/pietato-chromium ] && [[ "$out" == *DONE ]]'
run no "" ""
check "a Pi 3: nothing" '[ ! -s $D/log ] && [[ "$out" == *DONE ]]'
grep -qx 'ID=ubuntu' /etc/os-release || { echo "FAIL this machine isn't Ubuntu (for the PC's part)"; fails=$((fails + 1)); }
run yes "" "chromium" /etc/os-release
check "a PC with Ubuntu: chromium-browser at once (Ubuntu's snap), with its PAM service" \
  '[ "$(cat $D/log)" = "apt-get install -y cage xwayland wlr-randr fonts-liberation fonts-noto-color-emoji libpam-systemd
apt-get install -y chromium-browser" ] && [ -f $D/pam/pietato-chromium ] && [[ "$out" == *DONE ]]'
run yes "" "chromium-browser" /etc/os-release
check "...not to be had: it says so, and on to the rest" \
  '[[ "$out" == *"Couldn'"'"'t install Chromium"* ]] && [ ! -f $D/pam/pietato-chromium ] && [[ "$out" == *DONE ]]'
echo
if [ "$fails" = 0 ]; then echo "ALL OK"; else echo "FAILED: $fails"; fi
