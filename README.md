# Pietato

Turns your Raspberry Pi GPi Case 2W or GPi Case 2 into a pocket-sized smart media center. Versatile home
entertainment remote where you can watch live TV, stream videos, listen to music and radio, view photos, play
your own games, check the weather and system stats, and control your smart home through Home Assistant. It
works on any Raspberry Pi with a TV or monitor on HDMI too, and on a regular PC with Ubuntu.

<p>
  <img src="docs/tv.gif" height="260">
  <img src="docs/tv_remote.gif" height="260">
  <img src="docs/obsbot-controller.gif" height="260">
  <img src="docs/matrix.gif" height="260">
</p>

## Install

The easy way is an SD card image, for any 64-bit Pi (Zero 2 W, 3, 4, 5 or a Compute Module 4): from the
[latest release](https://github.com/frogCaller/pietato/releases/latest), the one ending in
`gpi-case-2w.img.xz` for the GPi Case 2W, `gpi-case-2.img.xz` for the GPi Case 2 (a Compute Module 4 without
eMMC starts from the card), or `hdmi.img.xz` for a TV or monitor. Write it to a microSD
card (8 GB or more) with [Raspberry Pi Imager](https://www.raspberrypi.com/software/), under Use custom,
adding your WiFi, time zone, username and password in its settings if you like (the WiFi can be set in
Pietato's Settings too). Without them, the user is `pi`, with no password until you set one
(`sudo passwd pi`).

Or set it up yourself, on Raspberry Pi OS Lite:

```
git clone https://github.com/frogCaller/pietato.git
cd pietato
sudo bash setup.sh
```

It asks if the Pi is in a GPi Case 2W (or, on a Compute Module 4, a GPi Case 2). If it is, it sets up the
case's screen, sound and power switch: turn the SAFE SHUTDOWN switch behind the cartridge to ON, and
switching the case off shuts the Pi down safely. If not, it leaves HDMI as it is.
In the GPi Case 2's dock, with the TV on, the picture is on the TV: put the case in the dock or take it out
and the Pi restarts with the picture where it should be. The case's buttons don't work in the dock, so use a
USB or Bluetooth controller there.
Then it installs `pitato.py` and the web page as services, sets the Pi to sign you in by
itself at start-up (`sudo bash setup.sh --login` keeps the password prompt), asks about the
optional parts, and reboots. The first time takes a while (an hour or more on a Pi 4, as it builds
the game emulators), so leave the Pi on until it says All set.

### On a PC

If you have a regular computer (Intel or AMD) with Ubuntu 24.04, Desktop or Server, you can run it there
too and play with a USB or Bluetooth controller. Set it up the same way:

```
git clone https://github.com/frogCaller/pietato.git
cd pietato
sudo bash setup.sh
```

It builds every game emulator (about half an hour), so leave the computer on until it says All set.
After that, the computer starts in Pietato, like a console. If you have Ubuntu's desktop, open System,
press SELECT for its list and pick Desktop to use it, then restart the computer to come back to Pietato.
Settings > Resolution sets the screen's size at start-up. With Ubuntu's desktop installed, Bluetooth
headphones only play sound on the desktop, so in Pietato use the computer's speakers, HDMI or a USB speaker.

Keep the `pietato` folder where it is: your settings live in its `static` folder. To update, press
Update software at the top of System's list (SELECT switches System between its dashboard and the list).
When there's a new version, the dashboard says so, and A updates from there too. It runs `git pull`, and
if that brings a new version, the Pi puts it in and restarts. Your settings stay as they are. If you
set it up before it had Update software, or when it was called gpi-media, run `git pull` and
`sudo bash setup.sh` once (from gpi-media, that moves everything across to the new name). If Update
software ever says the folder has changes of its own when you haven't changed anything, run
`git fetch` and `git reset --hard origin/main` in the `pietato` folder, then `sudo bash setup.sh --update`.

If you need all of your computer for something else for a while, run `sudo bash stop.sh` in the `pietato`
folder. Pietato stops and won't start with the computer (a PC starts in its desktop again) until
`sudo bash start.sh` turns it back on. If you'd rather not keep it, `sudo bash uninstall.sh` takes it off.
Your own files and the `pietato` folder stay, so delete the folder too if you don't need your settings.

It starts on a home screen of apps:

- **Home**: a remote for your TVs and your lights (through Home Assistant), a dashboard of your
  Pi-hole's stats (from the Pi-hole itself: add it by its address), and Web, for browsing (see Web below).
  Put in Home Assistant's IP address and a long-lived token in its Settings, last on its tab, or in the web
  page's Settings
- **TV**: Plex (Continue watching, Watchlist, Live TV with news and sports), Jellyfin, about 250 old
  cartoons and 150 old films from the Internet Archive, and your own streams
- **Music**, **Radio**, **Photos** (filters, delete), **Videos** (picks up where you left off)
- **Weather** (press START there to set where you are, and °F or °C), and **Finance**: stock and coin prices
  and charts. Press Y on Finance to look up more to add
- **Files**: PDFs, documents, text, pictures, video and music, on the Pi or on your other computers
- **Camera**: a USB camera plugged into the Pi (it shows up by itself), any camera on your network, or the ones
  on your other Pis: switch between them with L and R, steer an OBSBOT, take pictures, and have your bot say
  what it sees
- **Bot**: talks through Ollama on another computer, sees through your camera and takes pictures,
  out loud if you give it a voice. At work, it acts out what your coding agent is doing, rings a
  bell when it's done, and sends it prompts you type
- **Simulator**: Rock Paper Scissors (pick a winner before the first capture), Game of Life, Forest Fire
  and the Mandelbrot set, which takes you on dives (or press the d-pad to explore it, A to zoom in and
  Y to zoom out). Press SELECT to watch one full screen. It can also start cmatrix, hollywood, nyancat,
  cacafire and htop without a keyboard: in cmatrix, ◀▶ change its colour and ▲▼ its speed; in htop, ▲▼ move
  through what's running and X or Y sort it by CPU or memory; and B stops any of them
- **Games**: Snake (press X and a decision model on your bot's computer plays it for you), and your own
  Game Boy, Game Boy Advance, NES, SNES, Genesis, Master System, Game Gear and PlayStation games, and
  N64, PSP, DS and Dreamcast games on a Pi 4 or 5 or a PC. Two can play on two controllers
- **System**: a dashboard of the Pi's temperature, how busy it is, its memory, storage and network. SELECT
  shows it as a list instead, with Update software, Reboot and Shut down
- **Settings**: WiFi, Bluetooth, the home screen's style, background, colours, video size, a TV or monitor's
  resolution, sound, controller
- If you'd rather see the apps on the whole screen, set Settings > Full screen apps to On. The status
  bar, the tabs and the button hints go away, leaving just the app's name at the top. The buttons work
  the same, and L and R still switch apps
- If your screen is mounted on its side or upside down, Settings > Rotate screen turns the picture to
  match: the apps, games, videos and the console

![Media mode](docs/screens.png)

## Controllers

The GPi Case's own buttons, or any USB or Bluetooth game controller (Xbox, PlayStation,
8BitDo, the cheap SNES-style ones). Plug them in any time.

- Home switches between the apps and the console, where the buttons work as keys (Up for the last
  command, A for Enter). To start in the console instead, set Settings > At start-up to Terminal.
- If your controller is Bluetooth, put it in pairing mode and pick it in Settings > Bluetooth, or
  under Bluetooth on the web page. Keyboards and headphones pair the same way, and while headphones
  are connected, sound plays through them. If they disconnect, what's playing pauses. A USB speaker
  works the same way while it's plugged in.
- If A and B are the wrong way round, use that controller to set Settings > Swap A and B to On.
- If a button does the wrong thing, open Settings > Controller and press each button it asks for.
- If your controller has no Home button, press Select and Start together.
- A keyboard works the apps too: W A S D (or the arrow keys) is the d-pad, Enter or Space is A,
  Backspace or Esc is B, X and Y are X and Y, Q and E are L and R, P is Start and O is Select. Home
  stays on the controller. In the console, and in a box you're typing into, it types as usual.
- A trackpad (like the BB9900's) or a mouse works too: swipe to move, one step for a short swipe and a
  few for a long one, and press it to pick. The right button goes back.

## The web page

Open `http://<your Pi's IP address>:5432` on your phone or computer. Anyone on your WiFi
can open it, so if you share your WiFi, give it a password in the page's Settings.

**Screen** is the Pi's screen in media mode, and it works like the Pi: tap something on it to open
it, and swipe or scroll to move along a list. Back and Home are under it, and the whole remote is
behind Remote. When the Pi has a box to type in, one comes up under the screen too, so you can type
on your phone or computer. Further down, you can set up controllers and pair Bluetooth devices.

Under the screen there are three more buttons:

- **Play here**: what you pick plays on your phone or computer instead of the Pi. That's your videos
  and music, cartoons, films and radio, and NES, SNES, Game Boy, GBA, Genesis, Master System, Game
  Gear, PlayStation, N64 and DS games. Games play in [EmulatorJS](https://emulatorjs.org), which the
  Pi gets from npm the first time you play that kind of game (about 5 MB). A game's save comes from
  the Pi and goes back to it as you play, so you can carry on on the Pi. Plex, Jellyfin, live
  channels, PSP and Dreamcast games, and games in more than one file (a `.cue`) still play on the Pi.
- **Sound here**: the Pi's sound plays on your phone or computer instead of the Pi. It's a moment
  behind the picture.
- **Mic here**: the bot hears you through your phone's or computer's microphone instead of one
  plugged into the Pi (unless Settings > Bot > Listens is off). Browsers only let a page use your
  microphone over a secure connection, so the Pi has a secure page too:
  `https://<your Pi's IP address>:5443`. The first time, your browser warns you about it, because
  the Pi made its own certificate. Go on to the page from there.

If Sound here or Mic here says to run setup.sh again, run `sudo bash setup.sh` once more. It adds
the sound card they use.

**Library** puts cartoons, films, news, sports, radio or a camera on the Pi, and you can talk to your
bot there.

**Draw**, in Library, is paper the shape of the Pi's screen. Draw with your finger or the mouse, add
words or a photo, and press Show on the Pi: it stays on the screen until you press B, and it's kept
in `~/Pictures/Drawings`, so you can open it again in Photos. With Live on, it goes to the screen as
you draw. If you've set up a bot, Ask your bot has it say what it sees.

**Files** takes files or whole folders dropped on it. Music, videos, pictures, documents and games
each go to their own folder, and settings files like `radio.txt` go to Settings. Each file can
be shown on the Pi's screen, downloaded or deleted. The Computers tab has your other computers' files.

**Settings** has everything the Pi's Settings has, and each app's own: Home Assistant's address and
token, WiFi, Weather's place, the Bot's computer, your stocks and coins, and this page's password.
It's easier than the Pi's keyboard for pasting a token. Passwords and tokens can be put in or taken
off there, but the page never shows them.

## Cameras

Add a camera on the Camera tab or the web page by typing its address. It can be:

- any camera on your network: a webcam a script shares from another computer, an IP camera, an
  ESP32-CAM. Its address and port (like `192.168.1.20:5656`) is enough: the picture is found on its
  page. A link straight to its stream or picture works too.
- a Pi with a USB camera: run `sudo bash setup.sh --camera` on it. If the camera turns (an OBSBOT,
  a PTZ webcam), the d-pad steers it.

Pis running the camera server show up by themselves under On your network. If a camera is on its
side, press Y on it in your list of cameras to rotate its picture. If it turns the wrong way when you
steer it, press START on it there for its settings: Flip left and right, and Flip up and down.

## Games

Put your games in the `Games` folder in your home folder. It has a folder for each: `gb`, `gbc`, `gba`,
`nes`, `snes`, `genesis`, `sms`, `gg` and `ps1`, and on a Pi 4 or 5 or a PC, `n64`, `psp`, `nds` and `dc`. You
can also drop them on the web page (zips work too, for the cartridge ones). They're played by mGBA, Nestopia,
Snes9x, Genesis Plus GX, PCSX ReARMed, Mupen64Plus-Next, PPSSPP, melonDS and Flycast.

In a game, Home opens its menu: save or load a state, start over, the players, the volume, the picture
size, the AI player (see Bot below), or quit. For the picture, Fit keeps the game's shape, Sharp uses
whole pixels, and Fill fills the screen: on a TV an N64 game is drawn wide, and the others are
stretched. Each console keeps its own. Quitting keeps your place for next time. If you want to play
with someone, plug in or pair a second controller: the one that started the game is player 1, and the
next one to press a button is player 2 (an N64 or Dreamcast game takes four).

- N64: the right stick is the C buttons, and L2 is Z.
- DS (with the 64-bit Raspberry Pi OS): both screens side by side, and the right stick moves a pointer
  on the touch screen, with R2 to touch it.
- PlayStation: `.cue` and `.bin`, `.chd`, `.pbp` or `.m3u` files. Change discs in the game's menu.
- Dreamcast: `.gdi` (keep each game's tracks in a folder of its own), `.chd`, `.cdi` or `.cue` files. L
  and R are its triggers, as are L2 and R2.
- A BIOS isn't needed, but if you have one from your own console, put it in `Games/BIOS` and more
  PlayStation games work (for a Dreamcast, that's `dc_boot.bin`; a few games need it).

Press Y on the Games tab to find pictures of your games. If you have a lot of them, press Start to
search by name (or by console, like `gba`), and B to see them all again.

## Web

Web, in the Home tab, shows a page as its words, links and pictures, on any Pi. Sites made to be simple
work best, and a few are on its first page. Up and down go from link to link, A opens one, B goes back,
Start searches or goes to an address, Y bookmarks the page, and Select shows just the article.

On a Pi 4 or 5 or a PC, Web's first page opens Chromium too, for the sites that need it (setup.sh puts it in,
about 300 MB). The stick or the d-pad moves the pointer, A clicks, B goes back, and L and R scroll. X types into
the page and Start goes to an address, with Pietato's keyboard. Home opens its menu, for zoom, tabs, full
screen, or closing it. A keyboard and a mouse work in it too. If it doesn't start,
`journalctl -u pietato-chromium` says why.

## Other computers

If you want another computer's files on the Pi, open Files, then Other computers, and add it by its
address (like `192.168.1.20`). On Windows or a Mac, share a folder first; on Linux, turn on SSH. Its
files open read-only, so nothing on that computer is changed from the Pi.

## Bot

If you run [Ollama](https://ollama.com) on a computer on your network, set its address and a
model in Settings > Bot, or on the web page. On that computer Ollama has to listen on the
network (`OLLAMA_HOST=0.0.0.0`). The bot knows the time, the weather, your stocks and coins, and
what's playing. Ask it to take a picture and your camera takes one, into Photos and the conversation.

It also looks through your camera now and then and says what it sees, and looks at pictures you
send it: press X on the Bot page to pick one from Photos, or use the picture button on the web page
to send one from your phone. Press SELECT on the Camera tab, or Describe on the web page's Cameras,
and it says what that camera sees. It looks with the model you picked; if that model can't see
pictures, it tells you.

If that computer has a decision model (Ollama 0.35 or newer: `ollama pull nimble`), press X in
Snake and the model plays. Pick which one in Snake's options (START), and Slow if it can't keep up.

It can also play your games for you: in a game, open its menu with Home and press ▶ on AI player to
pick a decision model. Your buttons wait while it plays. In racing games, platformers, fighting games
and shooters it plays by instinct, many times a second: it holds the gas and steers along the road,
runs and jumps over gaps and enemies, attacks and blocks, or keeps firing, and the model says when to
play like that and when to press through a menu. In other games it looks at the screen and picks the
next button to press, while the game goes on at its own speed.

It plays Pokémon Emerald (the English cartridge) best, as there it reads the game's memory too. It
knows the story (out of the truck, the clock, your rival, Professor Birch, and on badge by badge) and
walks there by itself. It battles, reads, answers, heals when your team's badly hurt and trains in
tall grass when it's too weak for the next Gym, though it can't shop, catch Pokémon or solve every
puzzle yet.

In other games, your Bot's model coaches it. The first time, it says what kind of game it is, what each
button does and how it's played well; then every so often, and whenever it gets stuck, it looks at the
screen and works out what to aim for. What it works out goes in `Games/Saves`, in a file ending in
`.ai-notes.txt`, for next time. You can add your own tips there, under Tips, and change its Kind: line
if it got the kind of game wrong. What it saw and picked goes there too, in a file ending in `.ai.log`.

If you pick a voice in Settings > Bot > Voice, it says its replies out loud with
[Piper](https://github.com/rhasspy/piper), which runs on the Pi. The first time, the Pi
downloads Piper (about 25 MB) and the voice (about 60 MB). The quick voices suit a Pi Zero
best. Press SELECT to hear the last reply again, or Say it out loud on the web page.

If you plug a USB microphone into the Pi (one with a free USB port, so not in a GPi Case) or a PC, you
can talk to it: say "hey potato" and what you want. It makes out what you say on the Pi itself with
[Vosk](https://alphacephei.com/vosk/), which it downloads the first time you plug one in (about 45 MB), and
it doesn't listen while it's talking or something's playing. You can change the wake phrase in Settings >
Bot, or press X on the Bot page and Talk to it instead. Set Settings > Bot > Listens to Off to stop it, or
to On to have it use a webcam's microphone or a PC's built-in one too.

## Bot at work

Press left or right on the Bot to switch between chatting and work. At work it sits at a desk: it
reads when your coding agent reads, types when it writes code, waves when it needs you, and rings a
bell when it's done.

To connect Claude Code, run this on the computer it runs on:

```
curl -O http://<your Pi's IP address>:5432/coder_hooks.py
python3 coder_hooks.py <your Pi's IP address>
```

It adds hooks to Claude Code's settings that tell the Pi what Claude Code is doing. They run in
the background and do nothing when the Pi is off. `--remove` takes them out again.

The same script lets you send Claude Code prompts from the Pi. Start Claude Code like this:

```
claude --dangerously-load-development-channels server:pitato
```

Then press A at work, type a prompt, and press START. Claude Code gets it as if you had typed it.
This uses Claude Code's channels, which are a research preview: Claude Code asks you to confirm
each time it starts, and it needs to be signed in with a Claude account or an Anthropic API key.
If channels aren't available to you yet, Claude Code says so when it starts.

- If your web page has a password, add `--password` and the password.
- Prompts are only typed on the Pi itself. The web page's remote can't send them.
- If you only want the hooks, add `--no-prompts`.
- To have Claude Code use your Ollama models, start it with `ollama launch claude`
  ([Ollama's guide](https://docs.ollama.com/integrations/claude-code)). Prompts from the Pi
  need Claude Code signed in, though.
- Other agents and scripts can `POST /coder?pose=typing` (or `reading`, `thinking`, `done`...),
  and send a WAV to `POST /coder/say` to have it said out loud.

At work, A types a prompt, Y rings the bell, X turns its sounds off, and START shows these steps.

## Settings

All optional, in the `static` folder. Git leaves them out, so they stay off GitHub. The web page's
Settings writes most of them for you.

| File | What goes in it |
| --- | --- |
| `streams.txt`, `radio.txt` | your own streams and stations, `Name \| URL` per line |
| `finance.txt` | `stocks =` the stocks to show (tickers, as on Yahoo Finance) and `coins =` the coins (CoinGecko ids). Y on the Finance tab adds and removes them |
| `camera.txt` | `camera =` an address per line, a name after it if you like |
| `bot.txt` | `server =`, `model =`, `voice =`, `listen =` and `wake =` (Settings > Bot writes these) |
| `homeassistant.txt` | `url =` and `token =` (a long-lived access token): Settings > Home writes them, on the Pi or the web page. Your TVs and lights are found by themselves, and `tv =` and `lights =` pick which ones show |
| `pihole.txt` | `address =` and `password =`: the Pi-hole page writes them when you sign in there |
| `jellyfin.txt` | `server =` if your Jellyfin server isn't found by itself, and `user =` and `password =` if you'd rather not use Quick Connect |
| `webui.txt` | `password =` if you want the web page to ask for one, `hosts =` other names you open it by |

Plex signs in with a code at plex.tv/link. Jellyfin signs in with a Quick Connect code: in Jellyfin on
your phone or computer, open your profile, then Quick Connect, and type the code.

If a video is too big for the Pi to play smoothly (a 1080p film on a Pi Zero, or one in HEVC), the Pi
makes it smaller by itself in the background, in place of the original. On a Pi Zero a film can take
hours: it pauses while you watch or play something, carries on where it left off if you turn the Pi
off, and System shows how far it's got and how busy the CPU is.

## License

MIT, see [LICENSE](LICENSE). The fonts in `static/fonts` (Atkinson Hyperlegible Next and Inter) have their
own license, `OFL.txt`.
