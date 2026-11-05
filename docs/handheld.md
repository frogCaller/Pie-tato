# On an R36S

Pietato runs on the R36S and the handhelds like it, with the same chip (RK3326): the R33S, R35S, RG351MP, G350,
A10 Mini, RGB10 and the Odroid Go Advance and Super. They need [dArkOS](https://github.com/christianhaitian/dArkOS),
its Debian 13 image. Pietato knows it's on one as it starts, from the device tree.

The R36S has no WiFi of its own, so plug a USB WiFi dongle into it, and connect to your WiFi with Wifi in
dArkOS's Options menu. Enable Remote Services there lets you sign in over SSH, as `ark`. Then run the same
commands as on a Pi:

```
git clone https://github.com/frogCaller/Pietato.git
cd Pietato
sudo bash setup.sh
```

It doesn't ask about a GPi Case, and it uses dArkOS's own game emulators instead of building them, so the
first time takes about half an hour. N64, PSP, DS and Dreamcast games stay with dArkOS's EmulationStation.

After that, the handheld starts in Pietato instead of EmulationStation:

- The buttons work as they're printed, A on the right. FN is HOME, and so are SELECT and START together.
- The status bar shows the battery, and System shows it too, with the CPU's and GPU's temperatures.
- Settings > WiFi works through the dongle while it's plugged in.
- System > EmulationStation opens EmulationStation. Restarting the handheld comes back to Pietato.
- The web page's Sound here and Mic here don't work on it: its kernel has no Loopback sound card.

`sudo bash stop.sh` gives the handheld back to EmulationStation until `sudo bash start.sh`, and
`sudo bash uninstall.sh` takes Pietato off and leaves EmulationStation as it was.
