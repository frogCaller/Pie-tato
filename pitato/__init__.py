"""Pie-tato: game controller buttons as keys, plus a media mode. pitato.py starts it.

  theme.py          colours, fonts and the accent
  config.py         the static folder, settings files, saved settings
  util.py           small helpers: files, kinds of file, text, numbers
  net.py            machines on your network: addresses, requests
  system.py         this Pi's numbers, and WiFi
  bluetooth.py      Bluetooth: finding, pairing and connecting devices (BlueZ)
  screen.py         the screen, the framebuffer, sound outputs (Bluetooth headphones too), and a TV or
                    monitor's resolution
  radio.py          internet radio
  tv.py             the TV tab's shelves: old cartoons and films, live channels' words
  library.py        what's in each tab, and what plays things
  home.py           the home screen's icons and background
  weather.py        weather, and finding where you are
  documents.py      documents to text
  filters.py        photo filters
  cameras.py        the Camera tab's cameras
  nearby.py         what another Pi on your network has already fetched
  voice.py          the bot's voice (Piper)
  bot.py            the bot (Ollama)
  coder.py          the Bot at work
  crypto.py         coin prices (CoinGecko), for the Finance tab
  stocks.py         stock prices (Yahoo Finance), for the Finance tab
  homeassistant.py  the TV remote and lights (Home Assistant)
  plex.py           Plex
  jellyfin.py       Jellyfin
  computers.py      your other computers' files (shared folders, SSH), opened read-only
  shrink.py         big videos made smaller for this Pi, in the background
  update.py         System > Update software: a newer version (git), put in by setup.sh --update
  sims.py           the Simulator's worlds
  mandelbrot.py     the Mandelbrot set
  snake.py          Snake, and its AI's thread
  games.py          your own games: finding them and their emulators, one while it runs
  discs.py          disc games: PlayStation and PSP ones, and their game codes
  emulator.py       a game in a process of its own (libretro): its pictures, sound, saves
  gpu.py            the graphics chip, for a game drawn in 3D (an N64's, a PSP's)
  gameai.py         the AI player: a decision model on your bot's computer plays the game, looking at its screen
  anygame.py        ...any game: the next button to press, from what's on the screen
  emerald.py        ...Pokémon Emerald: from the game's memory too (emerald_maps.py: its maps' names)
  inputs.py         controllers, keys, the power switch
  control.py        the web page's requests
  media.py          media mode: class Media
  app.py            the main loop, and starting up
  screens/          media mode, a part for each app: its buttons and what it draws

Beside them, each run on its own:
  webui.py          the web page (port 5432): setup.sh makes it a service of its own
  camera.py         a Pi's USB camera on your network, for the Camera tab (setup.sh --camera)
  coder_hooks.py    Claude Code's hooks, telling the Bot what it's doing (the web page hands it out)
  convert_videos.sh videos made smaller on your computer (the Pi does it by itself too)
"""
