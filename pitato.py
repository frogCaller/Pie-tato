#!/usr/bin/env python3
"""
pitato.py - game controller buttons as keyboard keys, plus a media mode.

Made for the RetroFlag GPi Case 2W, and works on any Raspberry Pi with a screen: a TV or monitor
on HDMI, or the GPi Case's own. The menus are drawn at 640x480 and scaled up to fit.

Controllers: the GPi Case's buttons, or any USB or Bluetooth game controller (Xbox, PlayStation,
8BitDo, the cheap SNES-style ones...), plugged in or out at any time; a Bluetooth one (or a keyboard,
or anything else Bluetooth) is paired in Settings > Bluetooth, or on the web page. A and B the wrong
way round? Settings > Swap A and B swaps them on the controller you're holding (or Swap A and B next
to it on the web page), and keeps it for that controller. If a button does the wrong thing, Settings >
Controller sets yours up: press each button it asks for. No HOME button? Press SELECT and START
together. On the GPi Case, the star with HOME is HOME once, and the star on its own is HOME too, once
Settings > Controller has it (if the case sends it to the Pi at all).

The web page (webui.py) shows what's on the screen, has a remote, puts cartoons, films, news,
radio, apps and your own files on the screen, and pairs Bluetooth devices. It talks to this script on
127.0.0.1:5480.

While a video plays, Y turns full screen on or off (the choice is kept for the next videos);
Settings > Video size picks Fit (all of the picture), Full screen (zoomed) or Stretch.

It starts in media mode (Settings > At start-up can start it in the terminal instead).
Home button toggles between:
  terminal mode - buttons type keys in the console (arrows, Enter, Tab...)
  media mode    - opens on a home screen of app icons (d-pad and A to open one,
                  Y back to the console). Inside an app,
                  L/R switch apps, X shows the controls and B goes home.

Tabs (edit LIBRARY in pitato/library.py to change them):
  Home Assistant - one menu for (url and long-lived token in static/homeassistant.txt):
    TV Remote   - your TVs: arrows, OK, back, home, volume, power, inputs, and a number pad for
                  channels (SELECT, then Number pad); with more than one TV, SELECT switches
                  between them
    Lights      - your lights, smart plugs and scenes: A switches one on or off, left and
                  right dim it, and All lights off
  TV          - one menu for:
    Plex        - your Plex movies and shows, Continue watching, your Watchlist,
                  and Plex's free Live TV, with search; sign in once with a code at plex.tv/link
    Jellyfin    - your Jellyfin movies and shows and Continue watching, with search; the server
                  is found on your network, and you sign in once with a Quick Connect code
                  (or put server, user and password in static/jellyfin.txt)
    Cartoons    - about 250 old cartoons from the Internet Archive (Popeye, Looney Tunes, Superman,
                  Betty Boop, Casper...), listed in CLASSIC_TOONS below and streamed from
                  archive.org; plus the cartoon and anime channels on Plex's free Live TV
    Free Movies - about 150 old films from the Internet Archive (comedy, noir, horror, westerns,
                  silents), listed in FREE_FILMS below and streamed from archive.org;
                  plus the movie channels on Plex's free Live TV
    News        - the news channels on Plex's free Live TV
    Sports      - the sports channels on Plex's free Live TV
                  (Live TV needs you signed in to Plex, in TV > Plex)
    Streams     - your own list in static/streams.txt, one per line:  Name | URL
                  (a live .m3u8 plays the version that suits the Pi)
  Music       - files in ~/Music, keeps playing when you go back to the terminal; Settings > Random song
                at start-up plays one of them as it starts, then the rest in a random order, round and
                round (a list you pick goes round too), and music a game or a video stopped comes back
                after it, from where it was
  Radio       - real stations by genre, popular near you, or search by name (from the free
                Radio Browser directory), and your own list in static/radio.txt
  Camera      - cameras on your other Pis (PiE-ink, or this repo's camera.py: setup.sh
                --camera) or any MJPEG/JPEG link, listed in static/camera.txt or added by typing
                an address; L/R switch between them, the d-pad steers one that turns
                (an OBSBOT), A takes a picture into ~/Pictures; SELECT has the bot say what it
                sees, out loud with a voice (then holding START sets how fast one turns); Y
                rotates a camera's picture 90° (one on its side: Y on it in the list, B, if Y
                zooms it); ◀▶ on one in the list swaps left and right for one that turns the
                wrong way
  Photos      - pictures in ~/Pictures as a thumbnail grid, with zoom and slideshow;
                X adds a filter (saved as a copy), SELECT deletes
  Videos      - files in ~/Videos, resume where you left off; a video too big for the Pi to play
                smoothly is made smaller in the background, in place of the original
                (Settings > Big videos: Leave them, to keep them as they are)
  Games       - Snake: the d-pad steers it to the apples, each one makes it longer, and it's over when
                it runs into itself (or a wall: they can wrap round instead); A starts, pauses and plays
                again, Y is a new game, START has its speed, board and walls, SELECT is full screen.
                X hands it to a decision model (nimble, tev1...) on your bot's computer, through
                Ollama 0.35 or newer: told what each move would do (deadly, trapped, risky or safe, and
                nearer the apple or not), it picks the snake's moves, asked about where the snake will be by
                the time it answers; the game never waits for it (Keeps up: how many of the snake's
                moves it decided in time; for the rest it goes straight on). X again, and it's yours.
                START picks the model.
                Your own games, in the Games folder: Game Boy, GBA, NES, SNES, Genesis, Master System, Game
                Gear, PlayStation and (on a Pi 4 or 5) N64, PSP and DS play here (HOME is a game's menu: save
                states, discs, players, quit). Two players (four on an N64) each have a controller: the
                one that started the game is player 1, the next one pressed player 2. An N64
                game takes the sticks as they are: the right one is its C buttons (or R2 held with A B X Y),
                L2 is Z; on a controller with no stick, the d-pad is one. A PSP game's buttons go by where
                they are (the bottom one is Cross), and the left stick is its own. A DS game (melonDS, on the
                64-bit Raspberry Pi OS) shows both screens side by side (its menu's Screens: other ways);
                the right stick moves a pointer on the touch screen and R2 touches it (or the d-pad and A,
                with its menu's Touch screen), L2 blows on the microphone, the left stick is the d-pad
  Weather     - like PiE-ink's: now, the next hours, the week, and the US Weather
                Service's own words; the place is set in Settings
  Finance     - stock and coin prices with charts, laid out like PiE-ink's crypto screen (yours
                in static/finance.txt); Y looks stocks up on Yahoo Finance and coins on CoinGecko
                to add, or removes them
  Bot         - like PiE-ink's bot: a model on another computer running Ollama (Settings >
                Bot, or static/bot.txt) that knows the time, the weather, your stocks and coins,
                and what's playing, and now and then says something by itself; its face follows
                the tone of what it says. With a model that can see, it looks through your camera
                and says what it sees, and looks at a picture you send it from Photos (X); ask it
                to take a picture and your camera takes one, into Photos and the conversation.
                With a voice (Piper, on the Pi) it says its replies out loud; SELECT says the
                last one again. Left and right switch it between chat and work: at work it sits
                at a desk and acts out what your coding agent is doing: typing, reading,
                thinking, ringing its bell when it's done, waving when it needs you. Claude Code
                tells it through hooks that coder_hooks.py sets up on the computer it runs on;
                anything else can POST to the web page's /coder?pose=typing, and a WAV to
                /coder/say is said out loud. At work, A types a prompt for Claude Code (which
                takes it through coder_hooks.py's channel), Y rings the bell, X turns its sounds
                off, up and down set the volume, START shows how to connect an agent
  Simulator   - little worlds to watch, each in a box beside its numbers or full screen (SELECT):
    Rock Paper Scissors - pieces bounce around, and one hit by its counter switches sides until
                one team is left; left and right pick a winner before the first capture
    Game of Life - Conway's rules (or HighLife, Day & Night, Seeds), cells coloured by age
    Orbits      - planets round a sun pull on each other, and merge when they meet
    Forest Fire - trees grow, lightning strikes, fire spreads and the forest grows back
    Mandelbrot Set - dives into the set to one well-known place after another, down to a tiny copy
                of the set or as deep as the numbers go; or the d-pad explores it: A zooms in,
                Y out, for as long as they're held
                A pauses, X gives it a poke, Y starts it again, START has its options
  Files       - browse everything; opens photos, PDFs, documents, text, video, music; Other computers
                opens another computer's files by its address (Windows and Mac shared folders, or
                Linux over SSH), read-only
  System      - CPU temperature, WiFi, storage and more; reboot and shut down
  Settings    - WiFi (scan, connect, forget), Bluetooth (look, pair, connect, forget: a keyboard shows
                its code to type), the home screen's style (Bright, Glass, Minimal or Cards),
                background and colours, clock, location, units, video size, sound (Auto: Bluetooth
                headphones or a speaker while they're connected, else a TV on HDMI, else the Pi's own;
                or HDMI, headphones...),
                controller, swap A and B, start-up, and a random song at start-up. Bluetooth headphones
                gone while something plays: it pauses (A plays on through the Pi), a game's menu comes up

Your settings files (radio.txt, bot.txt...) are in the static folder of the pitato folder.
setup.sh tells the service where that is; run by hand, it's the static folder next to this script.

The code is in the pitato folder inside it, a file for each part (pitato/__init__.py says
which is which); this file starts it.

Setup:
    sudo apt install python3-evdev python3-pil python3-numpy fonts-dejavu-core \
                     mplayer poppler-utils
    sudo python3 pitato.py        # try it, Ctrl+C to stop
Optional: sudo apt install libreoffice-core libreoffice-writer libreoffice-calc
          libreoffice-impress  -> documents open with their real layout
          (slow the first time on a Pi Zero). Without it you get the text. (setup.sh installs it.)

If a button does the wrong thing, set it up in Settings > Controller (or fix CODES in pitato/inputs.py).
"""
import os
import sys

# the rest of it is the pitato package: next to this file (in the pitato folder), or where
# setup.sh puts it
for _where in (os.path.dirname(os.path.realpath(__file__)), "/usr/local/share/pitato"):
    if os.path.isfile(os.path.join(_where, "pitato", "__init__.py")):
        if _where not in sys.path:
            sys.path.insert(0, _where)
        break

from pitato.app import main  # noqa: E402

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
