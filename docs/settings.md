# Settings files

All optional, in the `static` folder. Git leaves them out, so they stay off GitHub. The web page's
Settings writes most of them for you.

| File | What goes in it |
| --- | --- |
| `streams.txt`, `radio.txt` | your own streams and stations, `Name \| URL` per line |
| `finance.txt` | `stocks =` the stocks to show (tickers, as on Yahoo Finance) and `coins =` the coins (CoinGecko ids). Y on the Finance tab adds and removes them |
| `camera.txt` | `camera =` an address per line, a name after it if you like |
| `bot.txt` | `server =`, `model =`, `style =`, `voice =`, `listen =`, `wake =`, `face_only =`, `colour =`, `background =`, `lashes =`, and its shape from 0 to 10: `eye_size =`, `eye_height =`, `eye_corners =`, `eye_gap =`, `mouth_size =` (Settings > Bot and its Character write these) |
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
