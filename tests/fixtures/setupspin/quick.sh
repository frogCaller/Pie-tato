#!/usr/bin/env bash
set -e
MACHINE="${MACHINE:-Pi}"     # (setup.sh sets it before this: the Pi, or on a PC the computer)
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
  if [ -n "$SWAPPED" ]; then swapoff "$SWAPPED" 2>/dev/null; rm -f "$SWAPPED"; fi   # (a build's swap file)
  if [ -n "$BUILDING" ]; then rm -rf "$BUILDING"; fi
  if [ "$FINISHED" != yes ]; then
    echo
    echo "setup.sh stopped before it was done. Run  sudo bash setup.sh  again to finish."
  fi
}
trap on_exit EXIT
trap 'exit 130' INT      # (Ctrl+C stops it, even when what was running when you pressed it took it in its stride)


log=$(mktemp "$VT/q-XXXXXX")
for n in $(seq 40); do working "Quick" "$log" true; working "Quick" "$log" false || true; done
rm -f "$log"; FINISHED=yes; echo "end"
