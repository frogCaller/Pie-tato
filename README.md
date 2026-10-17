# gpi-media

Turns a Raspberry Pi into a media player you work with a game controller or your phone.
Made for the RetroFlag GPi Case 2W with a Pi Zero 2 W, and works on any Pi with a TV or
monitor on HDMI.

The controller's buttons work as keys in the console (Up for the last command, A for Enter).
Press Home for media mode:

- **TV**: Plex (Continue watching, Watchlist, Live TV with news and sports), about 250 old
  cartoons and 150 old films from the Internet Archive, your own streams, and a TV remote
  through Home Assistant
- **Music**, **Radio**, **Photos** (filters, delete), **Videos** (picks up where you left off)
- **Weather**, and **Crypto**: coin prices and charts
- **Files**: PDFs, documents, text, pictures, video and music
- **Camera**: the cameras on your other Pis, or any camera link: switch between them with L and R,
  steer an OBSBOT, take pictures, and have your bot say what it sees
- **Bot**: talks through Ollama on another computer, sees through your camera and takes pictures,
  out loud if you give it a voice
- **System** and **Settings**: WiFi, background, colours, location, video size, sound, controller

![Media mode](docs/screens.png)

## Controllers

The GPi Case's own buttons, or any USB or Bluetooth game controller (Xbox, PlayStation,
8BitDo, the cheap SNES-style ones). Plug them in any time.

- If a button does the wrong thing, open Settings > Controller and press each button it asks for.
- If your controller has no Home button, press Select and Start together.

## The web page

Open `http://<your Pi's ip>:5432` on your phone or computer. Anyone on your WiFi
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
off shuts the Pi down safely. If not, it leaves HDMI as it is and opens media mode at start-up.
Then it installs `gpi_keys.py` and the web page as services, asks about the optional parts,
and reboots.

Keep the `gpi-media` folder where it is: your settings live in its `static` folder. To update
later, run `git pull` and `sudo bash setup.sh` again. Your settings stay as they are.

## Cameras

Add a camera on the Camera tab or the web page by typing its address. It can be:

- a Pi with a USB camera: run `sudo bash setup.sh --camera` on it.
  
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

If you pick a voice in Settings > Bot > Voice, it says its replies out loud with
[Piper](https://github.com/rhasspy/piper), which runs on the Pi. The first time, the Pi
downloads Piper (about 25 MB) and the voice (about 60 MB). The quick voices suit a Pi Zero
best. Press SELECT to hear the last reply again, or Say it out loud on the web page.

## Settings

All optional, in the `static` folder. Git leaves them out, so they stay off GitHub.

| File | What goes in it |
| --- | --- |
| `streams.txt`, `radio.txt` | your own streams and stations, `Name \| URL` per line |
| `crypto.txt` | `coins =` the coins to show (CoinGecko ids) |
| `camera.txt` | `camera =` an address per line, a name after it if you like |
| `bot.txt` | `server =`, `model =`, `eyes =` (a model that can see) and `voice =` (Settings > Bot writes these) |
| `homeassistant.txt` | `url =` and `token =` (a long-lived access token) |
| `webui.txt` | `password =` if you want the web page to ask for one, `hosts =` other names you open it by |

Plex signs in with a code at plex.tv/link.

## License

MIT, see [LICENSE](LICENSE). The font in `static/fonts` has its own license, `OFL.txt`.
