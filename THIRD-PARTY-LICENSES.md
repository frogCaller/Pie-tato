# Third-party licences

Pietato's own code is under the MIT licence ([LICENSE](LICENSE)). The SD card images also hold other people's
work, each under its own licence. This file and the `licenses` folder are on every card, in the Pietato folder,
and they come with each release.

## Built from source by setup.sh

These are in every SD card image. Each link goes to the exact version that's built. setup.sh shows how each one
is built, including the changes it makes (the files in `patches`, and FinalBurn Neo's font).

| What | For | Version | Licence | Full text |
| --- | --- | --- | --- | --- |
| [PCSX ReARMed](https://github.com/libretro/pcsx_rearmed/tree/c8816799b50388e61cfe237fe2cdbb7d8175f20a) | PlayStation | c8816799b50388e61cfe237fe2cdbb7d8175f20a | GPL 2 | [pcsx-rearmed.txt](licenses/pcsx-rearmed.txt) |
| [Mupen64Plus-Next](https://github.com/libretro/mupen64plus-libretro-nx/tree/12edd2c74a517ff86dfa8cfc71ad75e4c10486d5) | N64 | 12edd2c74a517ff86dfa8cfc71ad75e4c10486d5 | GPL 2 | [mupen64plus-next.txt](licenses/mupen64plus-next.txt) |
| [PPSSPP](https://github.com/hrydgard/ppsspp/tree/v1.20.4) | PSP | v1.20.4, with `patches/ppsspp-libretro-threads.patch` | GPL 2 | [ppsspp.txt](licenses/ppsspp.txt) |
| [FFmpeg, as PPSSPP builds it](https://github.com/hrydgard/ppsspp-ffmpeg) | PSP games' films | the version PPSSPP v1.20.4 names | LGPL 2.1 | [ffmpeg.txt](licenses/ffmpeg.txt) |
| [melonDS](https://github.com/libretro/melonDS/tree/66b5d2634cd0a79030562811e6e05f5532f800ba) | DS | 66b5d2634cd0a79030562811e6e05f5532f800ba | GPL 3 | [melonds.txt](licenses/melonds.txt) |
| [Flycast](https://github.com/flyinghead/flycast/tree/v2.7) | Dreamcast | v2.7 | GPL 2 | [flycast.txt](licenses/flycast.txt) |
| [Beetle NeoPop](https://github.com/libretro/beetle-ngp-libretro/tree/a50d5ac288a81f2104ddf43195a4efdd15c72227) | Neo Geo Pocket | a50d5ac288a81f2104ddf43195a4efdd15c72227 | GPL 2 | [beetle-neopop.txt](licenses/beetle-neopop.txt) |
| [Gambatte](https://github.com/libretro/gambatte-libretro/tree/77f2567d718b8973d02caa2daa8dce4953faf811) | The Game Boy's link cable | 77f2567d718b8973d02caa2daa8dce4953faf811, with `patches/gambatte-link.patch` | GPL 2 | [gambatte.txt](licenses/gambatte.txt) |
| [FinalBurn Neo](https://github.com/libretro/FBNeo/tree/16e0f2339591bc023d4560255c000e508417f562) | Neo Geo | 16e0f2339591bc023d4560255c000e508417f562 | FB Neo licence (not for sale), and the MAME licence | [fbneo.txt](licenses/fbneo.txt), [mame.txt](licenses/mame.txt) |
| [rcheevos](https://github.com/RetroAchievements/rcheevos/tree/1433173220a7eaede6a9ed7a18e94117be1821e0) | Achievements | 12.5.0, 1433173220a7eaede6a9ed7a18e94117be1821e0 | MIT | [rcheevos.txt](licenses/rcheevos.txt) |
| [cacafire, from libcaca](https://github.com/cacalabs/libcaca/blob/373c88b9890e67bde91e6acb8f1c442e847d1203/src/aafire.c) | The Simulator's cacafire | 373c88b9890e67bde91e6acb8f1c442e847d1203, without its "Powered by libcaca" line | LGPL 2 | [cacafire.txt](licenses/cacafire.txt) |

## From Raspberry Pi OS

The rest of what's on a card comes from Raspberry Pi OS, including the emulators setup.sh installs as packages:
mGBA (MPL 2.0), Nestopia UE (GPL 2), Snes9x (its own licence, not for commercial use) and Genesis Plus GX (its
own licence, not for commercial use). FFmpeg, MPlayer, Chromium, LibreOffice and the Simulator's programs come the
same way. Each package's licence is on the card in `/usr/share/doc/<package>/copyright`, and its source is
available from Raspberry Pi OS and Debian (`apt-get source <package>`).

## In this repository

- The fonts in `static/fonts` (Atkinson Hyperlegible Next and Inter): SIL Open Font License 1.1, in
  `static/fonts/OFL.txt`
- The console pictures in `pitato/icons/consoles`: RetroArch's, under CC BY 4.0, in
  `pitato/icons/consoles/CREDITS.txt`

## Only on a PC

On a PC, setup.sh also builds [Dolphin](https://github.com/libretro/dolphin/tree/b93001ed50c8b34e6ead4eed713c2005a80386e4)
(GameCube and Wii: GPL 2 or later) and [LRPS2](https://github.com/libretro/ps2/tree/1457fdf67885841c1b5299a95441532b3309eef7)
(PlayStation 2: GPL 3). They aren't in the SD card images.

## Fetched when you use them

The bot's voice (Piper, and the voice you pick) and its ears (Vosk, and its English model) are downloaded on the
Pi the first time you use them, each with its own licence. They aren't on the card.
