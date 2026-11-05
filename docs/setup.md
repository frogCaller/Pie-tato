# Setting it up

`sudo bash setup.sh`, in the Pietato folder, sets it up. The [README](../README.md#install) has the commands.

## Its questions

It starts with a few questions (the arrows, Space and Enter; Esc goes back). It asks if the Pi is in a GPi
Case 2W (or, on a Compute Module 4, a GPi Case 2). If it is, it sets up the case's screen, sound and power
switch: turn the SAFE SHUTDOWN switch behind the cartridge to ON, and switching the case off shuts the Pi down
safely. If not, it leaves HDMI as it is. Then Default puts in everything your Pi can run, and Custom lets you
pick, each part with how long it takes, so you can leave the big emulator builds out (the PSP's takes about an
hour on a Pi 4) and put them in another time. You can connect your Home Assistant, Pi-hole, Ollama, Plex,
Jellyfin and RetroAchievements there too, and give the web page a password, or do all that later in Settings.

Then it works by itself, a line for each step (all it does is in `/var/log/pietato-setup.log`): it installs
`pitato.py` and the web page as services, sets the Pi to sign you in by itself at start-up (untick that in
Custom, or run `sudo bash setup.sh --login`, to keep the password prompt), and restarts, unless you said not to.
The first time takes a while (an hour or more on a Pi 4 with everything in), so leave the Pi on until it says
All set.

## Screens

A small square screen (like Waveshare's 4-inch 720x720) may tell the Pi it's a TV, which squeezes the picture:
pick 720x720 (square) in Settings > Resolution. On a touch screen, tap what you want and swipe to move along
a list.

In the GPi Case 2's dock, with the TV on, the picture is on the TV: put the case in the dock or take it out
and the Pi restarts with the picture where it should be. The case's buttons don't work in the dock, so use a
USB or Bluetooth controller there.

## Running it again

Run it again whenever you like. What you left out stays out (with Update software too) until you put it back
in, and `sudo bash setup.sh --default` puts everything in. `--without ps1,psp` leaves parts out without asking
(the parts: `classic`, `ps1`, `n64`, `psp`, `nds`, `dc`, `ps2`, `gc`, `neogeo`, `ngp`, `link`, `cheevos`,
`chromium`, `office`, `toys`, `computers`), and `--plain` asks the old way, a question at a time.

## Updating

Keep the Pietato folder where it is: your settings live in its `static` folder. To update, press
Update software at the top of System's list (SELECT switches System between its dashboard and the list).
When there's a new release, the dashboard says so, and A updates from there too. It gets the
[latest release](https://github.com/frogCaller/Pietato/releases/latest), and if that's newer than what you have,
the Pi puts it in and restarts. Your settings stay as they are. Changes on GitHub that aren't in a release yet
wait for the next one.

If you set it up before it had Update software, or when it was called gpi-media, run `git pull` and
`sudo bash setup.sh` once (from gpi-media, that moves everything across to the new name). If Update
software ever says the folder has changes of its own when you haven't changed anything, run
`git fetch --tags --force` and `git reset --hard v1.2` in the Pietato folder (the latest release's name in
place of `v1.2`), then `sudo bash setup.sh --update`. That's also the way to update by hand.

## Stopping it, or taking it off

If you need all of your computer for something else for a while, run `sudo bash stop.sh` in the Pietato
folder. Pietato stops and won't start with the computer (a PC starts in its desktop again) until
`sudo bash start.sh` turns it back on. If you'd rather not keep it, `sudo bash uninstall.sh` takes it off.
Your own files and the Pietato folder stay, so delete the folder too if you don't need your settings.
