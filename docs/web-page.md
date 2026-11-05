# The web page

Open `http://<your Pi's IP address>:5432` on your phone or computer. Anyone on your WiFi
can open it, so if you share your WiFi, give it a password in the page's Settings. On a phone, you can add
it to your home screen (Share, then Add to Home Screen on an iPhone, or Add to Home screen in Chrome's menu)
and it opens like an app.

**Screen** is the Pi's screen in media mode, and it works like the Pi: tap something on it to open
it, and swipe or scroll to move along a list. Back and Home are under it, and the whole remote is
behind Remote. Its Hotkey is the controller's HOME (a game's menu, say), while Home under the screen
goes to the home screen. When the Pi has a box to type in, one comes up under the screen too, so you
can type on your phone or computer. Further down, you can set up controllers and pair Bluetooth devices.

When the Pi is at its terminal instead of media mode, Screen on the secure page (below) shows the
terminal. Type the password you sign in to the Pi with, and you can use it from there: click it and
type, or on a phone, type in the box under it. Esc, Tab, Ctrl+C and the arrows are under it too, and
Lock asks for the password again. Changing your Pi password locks it on every page. The plain page
only links to the secure one, so your password and what you type never cross your WiFi as they are.

Beside the screen (under it on a phone), On this computer (or On this phone) has three switches:

- **Play here**: what you pick plays on your phone or computer instead of the Pi. That's your videos
  and music, cartoons, films and radio, and NES, SNES, Game Boy, GBA, Genesis, Master System, Game
  Gear, PlayStation, N64 and DS games. Games play in [EmulatorJS](https://emulatorjs.org), which the
  Pi gets from npm the first time you play that kind of game (about 5 MB). A game's save comes from
  the Pi and goes back to it as you play, so you can carry on on the Pi. Plex, Jellyfin, live
  channels, Neo Geo, Neo Geo Pocket, PSP and Dreamcast games, and games in more than one file (a `.cue`)
  still play on the Pi.
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
