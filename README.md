# gpi-media

Turns a Raspberry Pi into a media player you work with a game controller or your phone.
Made for the RetroFlag GPi Case 2W with a Pi Zero 2 W, and works on any Pi with a TV or
monitor on HDMI.

<p>
  <img src="docs/tv.gif" height="260">
  <img src="docs/tv_remote.gif" height="260">
  <img src="docs/matrix.gif" height="260">
</p>

It starts on a home screen of apps:

- **TV**: Plex (Continue watching, Watchlist, Live TV with news and sports), about 250 old
  cartoons and 150 old films from the Internet Archive, your own streams, and a TV remote
  through Home Assistant
- **Music**, **Radio**, **Photos** (filters, delete), **Videos** (picks up where you left off)
- **Weather**, and **Crypto**: coin prices and charts. Press Y on Crypto to look up coins to add
- **Files**: PDFs, documents, text, pictures, video and music
- **Camera**: the cameras on your other Pis, or any camera link: switch between them with L and R,
  steer an OBSBOT, take pictures, and have your bot say what it sees
- **Bot**: talks through Ollama on another computer, sees through your camera and takes pictures,
  out loud if you give it a voice. At work, it acts out what your coding agent is doing, rings a
  bell when it's done, and sends it prompts you type
- **Simulator**: Rock Paper Scissors (pick a winner before the first capture), Game of Life, Orbits,
  Forest Fire and the Mandelbrot set, which takes you on dives (or press the d-pad to explore it,
  A to zoom in and Y to zoom out). Press SELECT to watch one full screen
- **Games**: Snake. Press X and a decision model on your bot's computer plays it for you
- **System** and **Settings**: WiFi, background, colours, location, video size, sound, controller

![Media mode](docs/screens.png)

## Controllers

The GPi Case's own buttons, or any USB or Bluetooth game controller (Xbox, PlayStation,
8BitDo, the cheap SNES-style ones). Plug them in any time.

- Home switches between the apps and the console, where the buttons work as keys (Up for the last
  command, A for Enter). To start in the console instead, set Settings > At start-up to Terminal.
- If a button does the wrong thing, open Settings > Controller and press each button it asks for.
- If your controller has no Home button, press Select and Start together.

## The web page

Open `http://<your Pi's name>.local:5432` on your phone or computer. Anyone on your WiFi
can open it, so if you share your WiFi, set a password in `webui.txt` (see Settings below).

**Screen** shows what's on the Pi's screen in media mode, has a remote, and puts cartoons,
films, news, sports, radio, a camera or any app on it. You can also talk to your bot there.

**Files** takes files or whole folders dropped on it. Music, videos, pictures and documents
each go to their own folder, and settings files like `radio.txt` go to Settings. Each file can
be shown on the Pi's screen, downloaded or deleted.

## Install

On Raspberry Pi OS Lite (Bookworm):

```
git clone https://github.com/frogCaller/gpi-media.git
cd gpi-media
sudo bash setup.sh
```

It asks if the Pi is in a GPi Case 2W. If it is, it sets up the case's screen, speaker and
power switch: turn the SAFE SHUTDOWN switch behind the cartridge to ON, and switching the case
off shuts the Pi down safely. If not, it leaves HDMI as it is.
Then it installs `gpi_keys.py` and the web page as services, sets the Pi to sign you in by
itself at start-up (`sudo bash setup.sh --login` keeps the password prompt), asks about the
optional parts, and reboots.

Keep the `gpi-media` folder where it is: your settings live in its `static` folder. To update
later, run `git pull` and `sudo bash setup.sh` again. Your settings stay as they are.

## Cameras

Add a camera on the Camera tab or the web page by typing its address. It can be:

- a Pi with a USB camera: run `sudo bash setup.sh --camera` on it. If the camera turns (an OBSBOT,
  a PTZ webcam), the d-pad steers it.
- any MJPEG or JPEG camera link, such as an ESP32-CAM's

Pis running the camera server show up by themselves under On your network.

## Bot

If you run [Ollama](https://ollama.com) on a computer on your network, set its address and a
model in Settings > Bot, or on the web page. On that computer Ollama has to listen on the
network (`OLLAMA_HOST=0.0.0.0`). The bot knows the time, the weather, your coins and what's
playing. Ask it to take a picture and your camera takes one, into Photos and the conversation.

With a model that can see (Gemma, LLaVA, Qwen-VL), it also looks through your camera now and then
and says what it sees, and looks at pictures you send it: press X on the Bot page to pick one from
Photos, or use the picture button on the web page to send one from your phone. Press SELECT on the
Camera tab, or Describe on the web page's Cameras, and it says what that camera sees.

If that computer has a decision model (Ollama 0.35 or newer: `ollama pull nimble`), press X in
Snake and the model plays. Pick which one in Snake's options (START), and Slow if it can't keep up.

If you pick a voice in Settings > Bot > Voice, it says its replies out loud with
[Piper](https://github.com/rhasspy/piper), which runs on the Pi. The first time, the Pi
downloads Piper (about 25 MB) and the voice (about 60 MB). The quick voices suit a Pi Zero
best. Press SELECT to hear the last reply again, or Say it out loud on the web page.

## Bot at work

Press left or right on the Bot to switch between chatting and work. At work it sits at a desk: it
reads when your coding agent reads, types when it writes code, waves when it needs you, and rings a
bell when it's done.

To connect Claude Code, run this on the computer it runs on:

```
curl -O http://<your Pi's IP address>:5432/coder_hooks.py
python3 coder_hooks.py <your Pi's address>
```

It adds hooks to Claude Code's settings that tell the Pi what Claude Code is doing. They run in
the background and do nothing when the Pi is off. `--remove` takes them out again.

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

All optional, in the `static` folder. Git leaves them out, so they stay off GitHub.

| File | What goes in it |
| --- | --- |
| `streams.txt`, `radio.txt` | your own streams and stations, `Name \| URL` per line |
| `crypto.txt` | `coins =` the coins to show (CoinGecko ids; Y on the Crypto tab adds and removes them) |
| `camera.txt` | `camera =` an address per line, a name after it if you like |
| `bot.txt` | `server =`, `model =`, `eyes =` (a model that can see) and `voice =` (Settings > Bot writes these) |
| `homeassistant.txt` | `url =` and `token =` (a long-lived access token) |
| `webui.txt` | `password =` if you want the web page to ask for one, `hosts =` other names you open it by |

Plex signs in with a code at plex.tv/link.

## License

MIT, see [LICENSE](LICENSE). The font in `static/fonts` has its own license, `OFL.txt`.
