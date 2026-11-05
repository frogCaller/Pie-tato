# Games

Put your games in the `Games` folder in your home folder. It has a folder for each: `gb`, `gbc`, `gba`,
`nes`, `snes`, `genesis`, `sms`, `gg`, `ngp`, `ngpc`, `neogeo` and `ps1`, and on a Pi 4 or 5 or a PC, `n64`,
`psp`, `nds` and `dc`, and on a PC, `ps2`, `gc` and `wii`. You can also drop them on the web page (zips work
too, for the cartridge ones). They're played by mGBA, Nestopia, Snes9x, Genesis Plus GX, Beetle NeoPop,
FinalBurn Neo, PCSX ReARMed, Mupen64Plus-Next, PPSSPP, melonDS, Flycast, and on a PC, LRPS2 and Dolphin
(and gambatte, for the Game Boy's link cable).

If you have more than a dozen games, the Games tab shows an icon for each console to pick from, plus
Recently played, Favourites and All games. In a folder, ◀ and ▶ jump by letter, and SELECT adds a game
to your favourites (or takes it out). START searches all your games by name.

In a game, Home opens its menu: save or load a state, start over, the players, the volume, the picture
size, the AI player (see [the Bot](bot.md)), or quit. For the picture, Fit keeps the game's shape, Sharp uses
whole pixels, and Fill fills the screen: on a TV an N64 game is drawn wide, and the others are
stretched. Each console keeps its own. Quitting keeps your place for next time. If you want to play
with someone, plug in or pair a second controller: the one that started the game is player 1, and the
next one to press a button is player 2 (an N64, Dreamcast, GameCube or Wii game takes four).

Your place is saved as you play too, every minute (every three for a big N64 or PSP game, so you don't feel
it), so a flat battery loses very little, and switching the case off saves it before the Pi shuts down. To
have the Pi start in the game you played last, right where you were, set Settings > At start-up to Game.

- N64: the right stick is the C buttons, and L2 is Z.
- DS (with the 64-bit Raspberry Pi OS): both screens side by side, and the right stick moves a pointer
  on the touch screen, with R2 to touch it.
- PlayStation: `.cue` and `.bin`, `.chd`, `.pbp` or `.m3u` files. Change discs in the game's menu.
- Dreamcast: `.gdi` (keep each game's tracks in a folder of its own), `.chd`, `.cdi` or `.cue` files. L
  and R are its triggers, as are L2 and R2.
- PlayStation 2 (on a PC): `.iso`, `.chd` (in the `ps2` folder), `.cso` or `.cue` files. It needs the BIOS
  from your own PS2 in `Games/BIOS` (a file like `scph39001.bin`).
- GameCube and Wii (on a PC): `.iso`, `.rvz`, `.gcz`, `.ciso` or `.wia` files, and `.gcm` for a GameCube or
  `.wbfs` for a Wii. L2 and R2 are a GameCube's triggers, and R is Z. For a Wii, your controller is a Wii
  remote with its nunchuk: the left stick is the nunchuk's, the right stick points at the screen, X and Y
  are C and Z, and R2 shakes the remote.
- Neo Geo (on a Pi 2 or newer): each game is a zip with the name FinalBurn Neo knows it by (like
  `mslug.zip`), and they need the Neo Geo's BIOS, `neogeo.zip`, in `Games/BIOS`. SELECT puts in a coin.
- Other than that, a BIOS isn't needed, but if you have one from your own console, put it in `Games/BIOS`
  and more PlayStation games work (for a Dreamcast, that's `dc_boot.bin`; a few games need it).

If you have two Pietatos, with Settings > Share with other Pietatos on, a game's menu has two more:

- **Play on another Pietato** carries the game on there from the same moment (◀▶ picks which one), and
  its menu there sends it back. HOME on a video or on Now playing has it too, for the video, song or
  station (so does X twice), and for a picture, a PDF, a document or some text you're looking at, HOME
  has **View on another Pietato**: it opens there where you were (the same page, zoom and place), and
  HOME there sends it back. **Send to another Pietato** gives it a copy to keep instead, in its Pictures
  (for a picture) or Documents (the rest), with a number added to the name if it already has one. A song
  of yours on Now playing has it too: a copy goes in its Music, and the song keeps playing here. HOME on a
  song picked in your Music list, or a picture picked in Photos, has the same menu for it, without opening
  it first: Play on another Pietato starts the song there, View on another Pietato shows the picture.
- **Play together** asks the other one to play too. In an NES, SNES, Genesis, Master System or Neo Geo
  game, it joins as player 2 (if it hasn't got the game, it's copied over). A Game Boy or Game Boy Color
  game has **Link cable** instead: you each play your own game, linked, to trade or battle Pokémon. It
  starts from the game's own save, so save in the game first, and what you traded is in your save after.

To play on a Pietato that has no controller (one on the TV, say) with another one's buttons, see
[Another Pietato](controllers.md#another-pietato).

Each Pietato's name has a dot beside it in its accent colour, so if you give each one its own colour in
Settings > Accent colour, you can tell them apart at a glance. Two with the same name also show the end of
their address after it, like `raspberrypi (.62)`.

Left on the home screen for five minutes while it's plugged in, your Bot gets bored, and one of the
things it does is play one of your games by itself ([The Bot](bot.md) has the rest). With the AI player
set up, it plays from where you were, on a copy of your saves; otherwise it's the game's own demo. START
plays it for real, and any other button goes back. Settings > Attract mode turns it off, or Games only
keeps it to games.

Press Y on the Games tab to find pictures of your games. If you have a lot of them, press Start to
search by name (or by console, like `gba`), and B to see them all again.

If you have a RetroAchievements account (it's free, at [retroachievements.org](https://retroachievements.org)),
sign in on the web page, in Settings > Achievements, and your games earn achievements as you play. Each one
shows at the top of the game when you get it, and Achievements in the game's menu lists them all. They're the
regular kind (not hardcore), so save states still work. Disc games in `.chd` files don't get them yet.
