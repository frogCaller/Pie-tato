"""Your own games: the ones in the Games folder, the emulators that play them (libretro cores, from
Debian's packages, and PCSX ReARMed, Mupen64Plus, PPSSPP, melonDS and Flycast, built by setup.sh), their pictures (box
art from libretro's thumbnails, found by No-Intro's and Redump's lists of games), and a game while it runs
(pitato/emulator.py, in a process of its own)."""
import array
import difflib
import glob
import hashlib
import io
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

from .config import CACHE_DIR, home_dir
from .discs import cue_files, cue_fixed, dc_title, DISC_EXTS, disc_info, disc_number, gdi_files, m3u_files
from .screen import slow_pi
from .util import UA

# what plays what: key, badge, name, the files, and the emulators (libretro cores), the first installed one.
GAME_SYSTEMS = [
    ("gb", "GB", "Game Boy", (".gb",), ("mgba", "gambatte", "sameboy", "gearboy")),
    ("gbc", "GBC", "Game Boy Color", (".gbc",), ("mgba", "gambatte", "sameboy", "gearboy")),
    ("gba", "GBA", "Game Boy Advance", (".gba",), ("mgba", "gpsp", "vba_next", "vbam")),
    ("nes", "NES", "NES", (".nes",), ("nestopia", "fceumm", "quicknes", "mesen")),
    ("snes", "SNES", "SNES", (".sfc", ".smc"), ("snes9x", "snes9x2010", "snes9x2005", "bsnes")),
    ("genesis", "MD", "Genesis / Mega Drive", (".md", ".gen", ".smd", ".bin"), ("genesis_plus_gx", "picodrive")),
    ("sms", "SMS", "Master System", (".sms",), ("genesis_plus_gx", "picodrive", "smsplus")),
    ("gg", "GG", "Game Gear", (".gg",), ("genesis_plus_gx", "picodrive")),
    ("n64", "N64", "Nintendo 64", (".z64", ".n64", ".v64"), ("mupen64plus_next", "parallel_n64")),
    ("ps1", "PS1", "PlayStation", (".cue", ".chd", ".pbp", ".m3u", ".iso", ".bin"),
     ("pcsx_rearmed", "swanstation", "mednafen_psx", "beetle_psx")),
    ("psp", "PSP", "PlayStation Portable", (".iso", ".cso", ".pbp", ".chd"), ("ppsspp",)),
    ("nds", "DS", "Nintendo DS", (".nds",), ("melonds", "melondsds", "desmume", "desmume2015")),
    ("dc", "DC", "Dreamcast", (".gdi", ".cdi", ".chd", ".cue", ".m3u"), ("flycast",)),
]
DISC_SYSTEMS = ("ps1", "psp", "dc")              # discs: what's in the file says (pitato/discs.py)
SHARED_EXTS = (".bin",)                          # a Genesis game's, or a PlayStation disc's: what's in it says which
GAME_EXTS = {e: s[0] for s in GAME_SYSTEMS if s[0] not in DISC_SYSTEMS for e in s[3]
             if e not in SHARED_EXTS}            # cartridges: a file says which (a zip too)
GENESIS_FOLDERS = ("genesis", "megadrive", "mega drive", "md", "sega genesis", "sega mega drive",
                   "sega - mega drive - genesis")   # (a .bin in one: a Genesis game, whatever it says)
NEEDS_3D = ("n64", "psp", "dc")   # drawn in 3D by the graphics chip: a Pi 4 or 5 (pitato/gpu.py)
FAST_PI_ONLY = NEEDS_3D + ("nds",)   # ...and a DS's two processors and screens: a Pi 4 or 5 too
ANALOG_SYSTEMS = ("n64", "psp", "nds", "dc")   # its games take the sticks as they are, not as the d-pad (a DS's:
                                         # the right one moves the pointer on its touch screen, pitato/screens/games.py)
OWN_FILES = ("n64", "psp", "dc")   # its emulator keeps files of its own (settings, shaders, a PSP's fonts, a
                                   # Dreamcast's clock): not in Games/BIOS
GAME_PLAYERS = {"nes": 2, "snes": 2, "genesis": 2, "sms": 2, "ps1": 2, "n64": 4, "dc": 4}   # how many play its games
                                                 # at once, each on a controller of their own (the rest: one, on any)
GAME_PACKAGES = {"mgba": "libretro-mgba", "nestopia": "libretro-nestopia", "snes9x": "libretro-snes9x",
                 "genesis_plus_gx": "libretro-genesisplusgx",
                 "mupen64plus_next": "mupen64plus_next", "pcsx_rearmed": "pcsx_rearmed", "ppsspp": "ppsspp",
                 "melonds": "melonds", "flycast": "flycast"}
DC_BIOS = ("dc_boot.bin", "dc_bios.bin")         # a Dreamcast's own BIOS, if it's in Games/BIOS (or Games/BIOS/dc):
                                                 # Flycast plays without it, and with it the few games that need it
GENERIC_NAMES = ("disc", "game", "gdi", "image")   # a .gdi named for what it is, not the game (GDEMU's disc.gdi): its
                                                   # folder's name instead (or the disc's own, its folder a number)
NEEDS_BIOS = {"mednafen_psx": ("scph5500.bin", "scph5501.bin", "scph5502.bin"),   # (the rest manage without)
              "beetle_psx": ("scph5500.bin", "scph5501.bin", "scph5502.bin")}
CORE_DIRS = ("/usr/lib/*/libretro", "/usr/lib/libretro", "/usr/local/lib/libretro",
             "/home/*/.config/retroarch/cores")
GAMES_FOLDER, SAVES_FOLDER, BIOS_FOLDER, IMAGES_FOLDER = "Games", "Saves", "BIOS", "Images"
GAME_DEPTH = 3           # folders inside the Games folder looked in, at most this deep
GAME_START = 15          # seconds a game has to start before it's given up on
GAME_QUIT = 6            # ...and to save and end when it's asked to


def system(key):
    return next(s for s in GAME_SYSTEMS if s[0] == key)


def playable(key):
    """A system this Pi plays. N64, PSP, DS and Dreamcast games need a Pi 4 or 5: on an older Pi they aren't shown at
    all."""
    return not (key in FAST_PI_ONLY and slow_pi())


def game_title(path):
    """A game's name: its file's, without the extension. A Dreamcast's disc.gdi (GDEMU's way): its folder's, or (a
    folder that's only a number) the name on the disc."""
    stem = os.path.splitext(os.path.basename(path))[0]
    if not path.lower().endswith(".gdi") or stem.lower().strip() not in GENERIC_NAMES:
        return stem
    folder = os.path.basename(os.path.dirname(os.path.abspath(path))).strip()
    if re.search(r"[^\W\d_]", folder) and folder.lower() not in (GAMES_FOLDER.lower(), "dc", "dreamcast"):
        return folder
    return dc_title(path) or (f"{folder} {stem}".strip() if folder else stem)


def games_dir():
    return os.path.join(home_dir(), GAMES_FOLDER)


_zips = {}                                         # a zip -> (its size and time, the system inside it)


def zip_system(path):
    """The system of the first game in a zip, or None."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (st.st_size, st.st_mtime)
    hit = _zips.get(path)
    if hit and hit[0] == key:
        return hit[1]
    found = None
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                ext = os.path.splitext(info.filename)[1].lower()
                found = GAME_EXTS.get(ext)
                if found and ext == ".md":                 # (a README, or a Mega Drive game?)
                    with z.open(info) as f:
                        found = None if markdown(info.filename, f.read(512)) else found
                if not found and ext in SHARED_EXTS and info.file_size <= GENESIS_MAX:
                    with z.open(info) as f:
                        found = "genesis" if genesis_header(f.read(0x110)) else None
                if found:
                    break
    except ZIP_TROUBLE:
        found = None                                   # (a zip with a password, squeezed some other way, or damaged)
    _zips[path] = (key, found)
    return found


GENESIS_MAX = 16 << 20                             # bytes: a Genesis game is a few MB at most (a disc's hundreds)
ZIP_TROUBLE = (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error, EOFError, ValueError)


def genesis_header(head):
    """A Genesis (Mega Drive) game's first bytes: "SEGA" in its header, at 256 (or just after)."""
    return b"SEGA" in head[0x100:0x110]


def markdown(name, head):
    """A .md that's text (a Markdown file, a README beside the games), not a Mega Drive game: a game's first bytes
    have zeros in them, text never does."""
    return name.lower().endswith(".md") and b"\0" not in head[:512]


def zip_game(z, exts):
    """A zip's game: the first of its files the system plays (a README.md beside it isn't one), or None."""
    for info in z.infolist():
        ext = os.path.splitext(info.filename)[1].lower()
        if ext not in exts or info.is_dir():
            continue
        if ext == ".md":
            with z.open(info) as f:
                if markdown(info.filename, f.read(512)):
                    continue
        return info
    return None


def genesis_bin(path, top=None):
    """A .bin that's a Genesis game, not a PlayStation disc's: SEGA in its header, or a Genesis folder it's in."""
    try:
        if os.path.getsize(path) > GENESIS_MAX:
            return False
        with open(path, "rb") as f:
            if genesis_header(f.read(0x110)):
                return True
    except OSError:
        return False
    rel = os.path.relpath(os.path.dirname(path), top) if top else os.path.dirname(path)
    return any(p.lower().strip() in GENESIS_FOLDERS for p in rel.replace("\\", "/").split("/"))


def game_kind(path, top=None):
    """A game's system (gb, ps1...) by its file (a disc's by what's in it), or None: it isn't one."""
    ext = os.path.splitext(path)[1].lower()
    if ext in GAME_EXTS:
        if ext == ".md":
            try:
                with open(path, "rb") as f:
                    if markdown(path, f.read(512)):
                        return None
            except OSError:
                return None
        return GAME_EXTS[ext]
    if ext == ".zip":
        return zip_system(path)
    if ext in SHARED_EXTS and genesis_bin(path, top or games_dir()):
        return "genesis"
    if ext in DISC_EXTS:
        kind = disc_info(path, top or games_dir())[0]
        return kind if kind in DISC_SYSTEMS else None
    return None


def disc_list(folder, base, discs):
    """An .m3u of a PlayStation game's discs (Disc 1, Disc 2...), kept with the cache: its path, or None."""
    where = os.path.join(CACHE_DIR, "games", "discs", hashlib.sha1(folder.encode()).hexdigest()[:10])
    path = os.path.join(where, base + ".m3u")
    try:
        discs = [cue_fixed(d, where) if d.lower().endswith(".cue") else d for d in discs]
    except OSError:
        pass
    text = "".join(d + "\n" for d in discs)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return path
    except OSError:
        pass
    try:
        os.makedirs(where, exist_ok=True)
        with open(path + ".part", "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(path + ".part", path)
        return path
    except OSError as ex:
        print(f"games: couldn't list {base}'s discs ({ex})", flush=True)
        return None


def one_per_game(found):
    """A PlayStation game's discs (its Disc 1, Disc 2... side by side) as one game, played from a list of them."""
    sets = {}
    for g in found:
        if g["system"] == "ps1":
            base, n = disc_number(g["title"])
            if n is not None:
                sets.setdefault((os.path.dirname(g["path"]), base, os.path.splitext(g["path"])[1].lower()), []).append((n, g))
    gone, out = set(), []
    for (folder, base, _), discs in sets.items():
        nums = [n for n, _ in discs]
        if len(discs) < 2 or len(set(nums)) != len(nums):
            continue
        discs.sort(key=lambda d: d[0])
        m3u = disc_list(folder, base, [g["path"] for _, g in discs])
        if m3u:
            gone.update(id(g) for _, g in discs)
            out.append({"path": m3u, "title": base, "system": "ps1", "discs": len(discs)})
    return [g for g in found if id(g) not in gone] + out


def find_games(folder=None):
    """[{"path", "title", "system"}] for the games in the Games folder (and folders in it), by name. A disc game's
    parts (a .cue's tracks, an .m3u's discs) aren't games of their own, and a PlayStation game's discs are one."""
    folder = folder or games_dir()
    files_seen = []
    top = folder.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in (SAVES_FOLDER, BIOS_FOLDER, IMAGES_FOLDER)
                         and root.count(os.sep) - top < GAME_DEPTH)
        files_seen += [os.path.join(root, n) for n in files if not n.startswith(".")]
    parts = set()                                      # (in lower case: a .cue made on Windows may say GAME.BIN)
    for path in files_seen:
        low = path.lower()
        if low.endswith(".cue"):
            parts.update(p.lower() for p in cue_files(path))
        elif low.endswith(".gdi"):
            parts.update(p.lower() for p in gdi_files(path))
        elif low.endswith(".m3u"):
            for disc in m3u_files(path):
                parts.add(disc.lower())
                if disc.lower().endswith(".cue"):
                    parts.update(p.lower() for p in cue_files(disc))
                elif disc.lower().endswith(".gdi"):
                    parts.update(p.lower() for p in gdi_files(disc))
    found = []
    for path in files_seen:
        if path.lower() in parts:
            continue
        sysk = game_kind(path, folder)
        if sysk and playable(sysk):
            found.append({"path": path, "title": game_title(path), "system": sysk})
    out = one_per_game(found)
    out.sort(key=lambda g: (g["title"].lower(), g["path"]))
    return out


def find_core(key):
    """The emulator (a libretro core's file) for a system, or None if none is installed."""
    for core in system(key)[4]:
        for pattern in CORE_DIRS:
            for path in sorted(glob.glob(os.path.join(pattern, core + "_libretro.so"))):
                if os.path.isfile(path):
                    return path
    return None


def bios_missing(core):
    """The BIOS file an emulator can't start without, when it isn't in Games/BIOS ('' when it's fine)."""
    need = NEEDS_BIOS.get(os.path.basename(core).replace("_libretro.so", ""), ())
    try:
        have = set(os.listdir(os.path.join(games_dir(), BIOS_FOLDER)))
    except OSError:
        have = set()
    return need[1] if need and not any(n in have for n in need) else ""


def save_name(path):
    """A game's name for its saves: its file's, without the extension (a Dreamcast's disc.gdi: its game's name, so two
    such games' saves are each their own)."""
    return game_title(path)


def has_resume(path):
    return os.path.isfile(os.path.join(games_dir(), SAVES_FOLDER, save_name(path) + ".state.auto"))


# ---- pictures: box art from libretro's thumbnails, the game known by No-Intro's and Redump's lists -----------
LIBRETRO_NAMES = {"gb": "Nintendo - Game Boy", "gbc": "Nintendo - Game Boy Color",
                  "gba": "Nintendo - Game Boy Advance", "nes": "Nintendo - Nintendo Entertainment System",
                  "snes": "Nintendo - Super Nintendo Entertainment System", "n64": "Nintendo - Nintendo 64",
                  "ps1": "Sony - PlayStation", "psp": "Sony - PlayStation Portable", "nds": "Nintendo - Nintendo DS",
                  "genesis": "Sega - Mega Drive - Genesis", "sms": "Sega - Master System - Mark III",
                  "gg": "Sega - Game Gear", "dc": "Sega - Dreamcast"}
N64_ORDERS = {b"\x37\x80\x40\x12": "H", b"\x40\x12\x37\x80": "I"}   # .v64, .n64: the bytes swapped in twos, fours
GAME_LISTS = "https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/{kind}/{system}.dat"
ART_SOURCES = ("https://thumbnails.libretro.com/{system}/{kind}/{name}.png",
               "https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/{kind}/{name}.png")
ART_KINDS = ("Named_Boxarts", "Named_Titles")    # the box, or else the title screen
ART_EXTS = (".png", ".jpg", ".jpeg")
ART_SIZE = 320           # pixels, at most, either way: a picture's kept this small
LIST_KEEP = 30 * 86400   # seconds a list of games is kept before it's fetched again
TAGS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
BAD_NAME_CHARS = re.compile(r'[&*/:`<>?\\|"]')   # (the thumbnails have _ for these)
NOT_THE_GAME = ("beta", "proto", "demo", "sample", "kiosk", "pirate", "unl", "aftermarket", "debug",
                "virtual console", "switch online", "classic mini", "collection", "program", "hack")
_art_index = {}                                     # the Images folder's pictures, as last looked at


def images_dir():
    return os.path.join(games_dir(), IMAGES_FOLDER)


def art_path(path):
    """A game's picture in Games/Images: named like the game's file (Tetris.gb.png), or without its
    extension (Tetris.png). .png or .jpg. None: there isn't one."""
    folder = images_dir()
    try:
        stamp = os.stat(folder).st_mtime
    except OSError:
        return None
    if _art_index.get("folder") != (folder, stamp):
        try:
            names = os.listdir(folder)
        except OSError:
            names = []
        _art_index.clear()
        _art_index["folder"] = (folder, stamp)
        _art_index["names"] = {n.lower(): n for n in names if os.path.splitext(n)[1].lower() in ART_EXTS}
    have = _art_index["names"]
    base = os.path.basename(path)
    for name in (base, os.path.splitext(base)[0]):
        for ext in ART_EXTS:
            hit = have.get((name + ext).lower())
            if hit:
                return os.path.join(folder, hit)
    return None


def plain_title(name):
    """A game's name without its tags: "Pokemon - Emerald Version (USA, Europe)" -> "Pokemon - Emerald Version"."""
    return TAGS.sub("", name).strip() or name


def title_words(name):
    """The words of a game's name, to compare: lower case, no tags or punctuation, "The" moved or dropped."""
    t = plain_title(name).lower()
    m = re.match(r"^(.*?), the\b(.*)$", t)               # "Legend of Zelda, The - ..." is "The Legend of Zelda - ..."
    if m:
        t = m.group(1) + m.group(2)
    t = re.sub(r"[^a-z0-9]+", " ", t.replace("&", " and ").replace("'", ""))
    return tuple(w for w in t.split() if w != "the")


def name_rank(name):
    """Lower is likelier the one you have: a finished game, then USA, World, Europe, then the rest."""
    tags = " ".join(re.findall(r"\(([^)]*)\)", name)).lower()
    odd = any(w in tags for w in NOT_THE_GAME)
    region = 0 if "usa" in tags else 1 if "world" in tags else 2 if "europe" in tags else 3
    return (odd, region, "rev" in tags, len(name))


def code_key(code, key="ps1"):
    """A game's code, the same however it's written: SLUS_005.94 and SLUS-00594 are SLUS-00594. A Dreamcast's: its
    letters and numbers, without Sega's MK (its disc says MK-51064, Redump's list 51064). None: it isn't one."""
    c = (code or "").upper().strip()
    if key == "dc":
        c = re.sub(r"[^A-Z0-9]", "", c.split("(")[0])
        c = c[2:] if c.startswith("MK") and c[2:].isdigit() else c
        return c if re.search(r"\d{3}", c) else None
    m = re.match(r"([A-Z]{4})[-_ ]?(\d{3})\.?(\d{2})\b", c)
    return f"{m.group(1)}-{m.group(2)}{m.group(3)}" if m else None


def read_game_codes(text, key="ps1"):
    """[(name, code)] from Redump's list: each game's name, and its code (SLUS-00594..., a Dreamcast's 51064...)."""
    out, name, inside = [], None, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("game ("):
            inside, name = True, None
        elif inside and s.startswith('name "') and name is None:
            name = s[6:-1] if s.endswith('"') else s[6:]
        elif inside and s.startswith('serial "') and name:
            code = code_key(s[8:-1] if s.endswith('"') else s[8:], key)
            if code:
                out.append((name, code))
        elif s == ")":
            inside = False
    return out


def read_game_list(text):
    """[(name, crc)] from a No-Intro list (clrmamepro's .dat): each game's name, and its files' checksums."""
    out, name, inside = [], None, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("game ("):
            inside, name = True, None
        elif inside and s.startswith('name "') and name is None:
            name = s[6:-1] if s.endswith('"') else s[6:]
        elif inside and s.startswith("rom (") and name:
            m = re.search(r"\bcrc ([0-9A-Fa-f]{8})\b", s)
            if m:
                out.append((name, m.group(1).upper()))
        elif s == ")":
            inside = False
    return out


def n64_crc(data):
    """An N64 game's checksum as No-Intro lists it: of its bytes in .z64 order (a .v64's or .n64's put right)."""
    kind = N64_ORDERS.get(bytes(data[:4]))
    if kind:
        a = array.array(kind)
        a.frombytes(data[:len(data) // a.itemsize * a.itemsize])
        a.byteswap()
        data = a.tobytes()
    return "%08X" % (zlib.crc32(data) & 0xFFFFFFFF)


def game_crcs(path, key):
    """The checksums a game may be listed under: its file's (a zip's: the game's inside it), a SNES
    game's without the 512 bytes some copiers put at the front, and an N64 game's in .z64 order."""
    out = []
    exts = system(key)[3]                              # (a zip's game: the first of the files its system plays)
    try:
        if key == "n64":
            if path.lower().endswith(".zip"):
                with zipfile.ZipFile(path) as z:
                    info = zip_game(z, exts)
                    return [n64_crc(z.read(info))] if info is not None else []
            with open(path, "rb") as f:
                return [n64_crc(f.read())]
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                info = zip_game(z, exts)
                if info is None:
                    return []
                out.append("%08X" % info.CRC)
                if key == "snes" and info.file_size % 1024 == 512:
                    out.append("%08X" % (zlib.crc32(z.read(info)[512:]) & 0xFFFFFFFF))
                return out
        size = os.path.getsize(path)
        whole, rest = 0, 0
        with open(path, "rb") as f:
            first = True
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                whole = zlib.crc32(chunk, whole)
                if key == "snes" and size % 1024 == 512:
                    rest = zlib.crc32(chunk[512:] if first else chunk, rest)
                first = False
        out.append("%08X" % (whole & 0xFFFFFFFF))
        if key == "snes" and size % 1024 == 512:
            out.append("%08X" % (rest & 0xFFFFFFFF))
    except ZIP_TROUBLE:
        pass
    return out


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


class GameList:
    """No-Intro's list of a system's games (Redump's, for discs) from libretro's database, kept a month: by
    checksum, by game code, and by the words of each name."""

    def __init__(self, key):
        self.key = key
        self.by_crc, self.by_code, self.names, self.words, self.mains = {}, {}, [], {}, {}

    def load(self):
        """True if it's here (fetched, or kept from before)."""
        system_name = LIBRETRO_NAMES[self.key]
        cache = os.path.join(CACHE_DIR, "games", system_name + ".dat")
        text = None
        try:
            if time.time() - os.path.getmtime(cache) < LIST_KEEP:
                text = open(cache, encoding="utf-8", errors="replace").read()
        except OSError:
            pass
        if text is None:
            try:
                kind = "redump" if self.key in DISC_SYSTEMS else "no-intro"
                data = fetch(GAME_LISTS.format(kind=kind, system=urllib.parse.quote(system_name)), timeout=60)
                text = data.decode("utf-8", errors="replace")
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                with open(cache + ".part", "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(cache + ".part", cache)
            except (OSError, urllib.error.URLError, ValueError) as ex:
                print(f"games: no list of {system_name} games ({ex})", flush=True)
                try:
                    text = open(cache, encoding="utf-8", errors="replace").read()   # (an old one will do)
                except OSError:
                    return False
        for name, crc in read_game_list(text):
            self.by_crc.setdefault(crc, name)
            if name not in self.words:
                self.add(name)
        if self.key in DISC_SYSTEMS:
            for name, code in read_game_codes(text, self.key):
                names = self.by_code.setdefault(code, [])
                if name not in names:
                    names.append(name)
        return True

    def add(self, name):
        self.names.append(name)
        self.words[name] = title_words(name)
        self.mains[name] = title_words(plain_title(name).split(" - ")[0])   # (its name before a subtitle)

    def by_name(self, title):
        """The game a file's name most likely is, or None: the same words; or the same words before its
        subtitle; or (two words or more) all its words and the fewest others."""
        want = title_words(title)
        if not want:
            return None
        for table in (self.words, self.mains):
            same = [n for n in self.names if table[n] == want]
            if same:
                return min(same, key=name_rank)
        if len(want) < 2:
            return None                                # (one word on its own could be anything)
        need = set(want)
        best = None
        for n in self.names:
            have = self.words[n]
            if need <= set(have) and len(have) - len(want) <= 3:
                score = (len(have) - len(want),) + name_rank(n)
                if best is None or score < best[0]:
                    best = (score, n)
        if best and difflib.SequenceMatcher(None, " ".join(want), " ".join(self.words[best[1]])).ratio() >= 0.5:
            return best[1]
        return None


def which_game(game, lists):
    """(the system's key, the game's name in No-Intro's or Redump's list) for one of your games: by its
    checksum (a disc's by the code on it), else by its file's name; or the file's own name, as a last try."""
    stem = game_title(game["path"])
    if game["system"] in DISC_SYSTEMS:
        key = code_key(disc_info(game["path"])[1], game["system"])
        for gl in lists:
            names = gl.by_code.get(key) if key else None
            if names:
                want = title_words(stem)
                same = [n for n in names if title_words(n) == want]
                return gl.key, min(same or names, key=name_rank)
    crcs = game_crcs(game["path"], game["system"]) if game["system"] not in DISC_SYSTEMS else []
    for gl in lists:
        for c in crcs:
            if c in gl.by_crc:
                return gl.key, gl.by_crc[c]
    for gl in lists:
        hit = gl.by_name(stem)
        if hit:
            return gl.key, hit
    return game["system"], stem


REGIONS = ("usa", "europe", "japan", "world", "australia", "canada", "asia", "korea", "germany", "france",
           "spain", "italy", "uk", "brazil", "china", "netherlands", "sweden")


def art_names(name):
    """A game's name, then the ways its picture may be named instead (libretro's pictures lag Redump's names:
    a game Redump calls '(USA, Canada) (En,Fr,Es)' may be '(USA) (En,Fr,Es)' there)."""
    out = [name]
    tags = re.findall(r"\(([^)]*)\)", name)
    region = next((t for t in tags if t.split(",")[0].strip().lower() in REGIONS), None)
    if region and "," in region:
        first = region.split(",")[0].strip()
        out.append(name.replace(f"({region})", f"({first})", 1))
        out.append(f"{plain_title(name)} ({first})")
    elif region:
        out.append(f"{plain_title(name)} ({region})")
    seen = set()
    return [n for n in out if not (n in seen or seen.add(n))]


def fetch_art(key, name):
    """A picture of the game (its box, or its title screen) from libretro's thumbnails: PNG bytes, or None."""
    system_name = LIBRETRO_NAMES[key]
    repo = system_name.replace(" - ", "_-_").replace(" ", "_")
    for kind in ART_KINDS:
        for each in art_names(name):
            file_name = urllib.parse.quote(BAD_NAME_CHARS.sub("_", each))
            for src in ART_SOURCES:
                url = src.format(system=urllib.parse.quote(system_name), kind=kind, name=file_name, repo=repo)
                try:
                    data = fetch(url)
                except urllib.error.HTTPError:
                    continue                           # (not there: the next place)
                except (OSError, urllib.error.URLError, ValueError):
                    continue
                if data[:8] == b"\x89PNG\r\n\x1a\n":
                    return data
    return None


def save_art(game, data, by_file_name=False):
    """A picture kept in Games/Images, small, named like the game (with its extension, if another game
    has the same name). Returns its path."""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
    img.thumbnail((ART_SIZE, ART_SIZE))
    folder = images_dir()
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
        try:
            st = os.stat(games_dir())
            os.chown(folder, st.st_uid, st.st_gid)
        except OSError:
            pass
    base = os.path.basename(game["path"])
    path = os.path.join(folder, (base if by_file_name else os.path.splitext(base)[0]) + ".png")
    tmp = os.path.join(folder, "." + os.path.basename(path) + ".part")
    try:
        img.save(tmp, "PNG")
        try:
            st = os.stat(folder)
            os.chown(tmp, st.st_uid, st.st_gid)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


class ArtFinder:
    """Finds pictures for the games that don't have one yet, a game at a time, on a thread of its own."""

    def __init__(self):
        self.busy = False
        self.done = self.total = self.found = 0
        self.note = ""                               # what it says when it's done (taken once)
        self.on_change = lambda: None

    def start(self, games):
        """False if it's busy already, or every game has a picture."""
        todo = [g for g in games if not art_path(g["path"])]
        if self.busy or not todo:
            return False
        self.busy, self.done, self.total, self.found, self.note = True, 0, len(todo), 0, ""
        threading.Thread(target=self.run, args=(todo, games), daemon=True).start()
        return True

    def run(self, todo, games):
        stems = {}
        for g in games:
            s = os.path.splitext(os.path.basename(g["path"]))[0].lower()
            stems[s] = stems.get(s, 0) + 1
        lists, reached = {}, False
        try:
            for g in todo:
                keys = ("gb", "gbc") if g["system"] in ("gb", "gbc") else (g["system"],)
                for k in keys:
                    if k not in lists:
                        gl = GameList(k)
                        lists[k] = gl if gl.load() else None
                key, name = which_game(g, [lists[k] for k in keys if lists[k]])
                data = fetch_art(key, name)
                if data is None and key != g["system"]:
                    data = fetch_art(g["system"], name)
                if data is not None:
                    reached = True
                    try:
                        save_art(g, data, stems.get(os.path.splitext(os.path.basename(g["path"]))[0].lower(), 0) > 1)
                        self.found += 1
                    except (OSError, ValueError) as ex:
                        print(f"games: couldn't keep the picture for {g['path']} ({ex})", flush=True)
                self.done += 1
                self.on_change()
            if self.found:
                self.note = (f"Found pictures for all {self.total} games" if self.found == self.total else
                             f"Found pictures for {self.found} of {self.total} games")
            elif not reached and not any(lists.values()):
                self.note = "Couldn't reach the picture library. Check the WiFi"
            else:
                self.note = "No pictures found for these games"
        except Exception as ex:                          # (never leaves it stuck on "busy")
            print(f"games: finding pictures: {ex!r}", flush=True)
            self.note = "Couldn't find pictures just now"
        finally:
            self.busy = False
            self.on_change()


def psp_files(sysdir, core):
    """PPSSPP's own files (the PSP's fonts, its pictures for messages), set up beside it by setup.sh: where it
    looks for them, its folder in the one it's given (a link to them)."""
    link, have = os.path.join(sysdir, "PPSSPP"), os.path.join(os.path.dirname(core), "PPSSPP")
    try:
        if os.path.islink(link) and not os.path.exists(link):
            os.remove(link)                              # (they've moved)
        if not os.path.lexists(link) and os.path.isdir(have):
            os.symlink(have, link)
    except OSError as ex:
        print(f"games: no PSP fonts for PPSSPP ({ex})", flush=True)


def dc_files(sysdir):
    """A Dreamcast's BIOS (Games/BIOS/dc_boot.bin, or in Games/BIOS/dc), where Flycast looks for it: the dc folder in
    the one it's given (a link to it). None there: Flycast plays with its own (and a link's gone when the BIOS is)."""
    folder = os.path.join(sysdir, "dc")
    bios = os.path.join(games_dir(), BIOS_FOLDER)
    have = {}
    for where in (os.path.join(bios, "dc"), bios):    # (Games/BIOS's own first)
        try:
            have.update({n.lower(): os.path.join(where, n) for n in os.listdir(where)})
        except OSError:
            pass
    try:
        os.makedirs(folder, exist_ok=True)
        for name in DC_BIOS:
            link, want = os.path.join(folder, name), have.get(name)
            want = want if want and os.path.isfile(want) else None
            if os.path.islink(link) and os.readlink(link) != want:
                os.remove(link)                        # (moved, or gone)
            if want and not os.path.lexists(link):
                os.symlink(want, link)
    except OSError as ex:
        print(f"games: no Dreamcast BIOS for Flycast ({ex})", flush=True)


def built_for_other_pi(core):
    """An emulator built for another kind of Pi's memory pages (Flycast, setup.sh notes them: a Pi 5's are bigger
    than a Pi 4's), so it wouldn't run here: True. (Nothing noted: False.)"""
    name = os.path.basename(core).replace("_libretro.so", "")
    try:
        with open(os.path.join(os.path.dirname(core), name + ".version")) as f:
            words = f.read().split()
    except OSError:
        return False
    if "pages" not in words[:-1]:
        return False
    try:
        return int(words[words.index("pages") + 1]) != os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return False


class GameRun:
    """A game while it runs: the emulator's process, and what it says. The buttons and the menu's
    asks go to it a line at a time; its answers come back on a thread of their own."""

    def __init__(self, game, on_change=lambda: None):
        self.game = game                             # {"path", "title", "system"}
        self.on_change = on_change
        self.p = None
        self.state = "starting"                      # starting, on, paused, done
        self.error = ""
        self.resumed = False
        self.slow = False                            # it was behind before its menu came up
        self.disc = (0, 1)                           # the disc in (from 0), of how many
        self.answers = []                            # what it said that hasn't been asked about
        self.cond = threading.Condition()
        self.writing = threading.Lock()              # (a line at a time: an AI player sends from its own thread)
        self.ended = False                           # it's gone (quit, or it stopped)

    def start(self, core, sound="", volume=80, picture="Fit", fb="/dev/fb0", resume=True, options=(), turn=0):
        """options: the emulator's settings ("key=value"), over what it'd have otherwise (a DS game's screens).
        turn: degrees the screen's picture is turned clockwise (a screen on its side: Settings > Rotate screen)."""
        exts = ",".join(system(self.game["system"])[3])
        saves = os.path.join(games_dir(), SAVES_FOLDER)
        own = self.game["system"] in OWN_FILES          # (Mupen64Plus: its settings, its shaders)
        sysdir = (os.path.join(CACHE_DIR, "games", self.game["system"]) if own
                  else os.path.join(games_dir(), BIOS_FOLDER))
        if own:
            os.makedirs(sysdir, exist_ok=True)
            if self.game["system"] == "psp":
                psp_files(sysdir, core)
            elif self.game["system"] == "dc":
                dc_files(sysdir)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ)
        env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        cmd = [sys.executable, "-m", "pitato.emulator", "--core", core, "--game", self.game["path"],
               "--exts", exts, "--saves", saves, "--name", save_name(self.game["path"]),
               "--system", sysdir, "--fb", fb, "--sound", sound or "",
               "--volume", str(int(volume)), "--picture", picture]
        if resume:
            cmd.append("--resume")
        if turn:
            cmd += ["--turn", str(int(turn))]
        for o in options:
            cmd += ["--option", o]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True,
                                  bufsize=1, cwd=root)
        threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        """What the emulator says, as it says it."""
        try:
            for line in self.p.stdout:
                words = line.split(None, 1)
                if not words:
                    continue
                what, rest = words[0], (words[1].strip() if len(words) > 1 else "")
                with self.cond:
                    if what == "ready":
                        self.state, self.resumed = "on", rest == "resumed"
                    elif what == "paused":
                        self.state, self.slow = "paused", rest == "slow"
                    elif what == "resumed":
                        self.state = "on"
                    elif what == "disc":
                        try:
                            i, n = (int(x) for x in rest.split()[:2])
                            self.disc = (i - 1, n)
                        except ValueError:
                            pass
                    elif what == "error" and self.state == "starting":
                        self.error = rest
                    elif what == "failed":                 # (it ended itself as it started)
                        self.error = rest
                    self.answers.append((what, rest))
                    self.cond.notify_all()
                self.on_change()
        except (OSError, ValueError):
            pass
        finally:
            try:
                self.p.wait(timeout=GAME_QUIT)
            except subprocess.TimeoutExpired:
                pass
            with self.cond:
                self.ended = True
                self.state = "done"
                self.cond.notify_all()
            self.on_change()

    def send(self, line):
        if self.p is None or self.ended:
            return False
        try:
            with self.writing:
                self.p.stdin.write(line + "\n")
                self.p.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def ask(self, line, wants, timeout=3.0):
        """Send a line, and wait for one of the answers wanted: (it, the rest) or (None, "")."""
        with self.cond:
            self.answers = [a for a in self.answers if a[0] not in wants]
        if not self.send(line):
            return None, ""
        end = time.monotonic() + timeout
        with self.cond:
            while True:
                hit = next((a for a in self.answers if a[0] in wants), None)
                if hit:
                    self.answers.remove(hit)
                    return hit
                left = end - time.monotonic()
                if left <= 0 or self.ended:
                    return None, ""
                self.cond.wait(left)

    def wait_started(self, timeout=GAME_START):
        """True once it's playing; False if it couldn't start (self.error says why)."""
        end = time.monotonic() + timeout
        with self.cond:
            while self.state == "starting" and not self.ended:
                left = end - time.monotonic()
                if left <= 0:
                    break
                self.cond.wait(left)
            return self.state in ("on", "paused")

    def press(self, name, port=0):
        """A button down: player 1's, or another player's (port 1 is player 2)."""
        self.send(f"down {name} {port}" if port else "down " + name)

    def release(self, name, port=0):
        self.send(f"up {name} {port}" if port else "up " + name)

    def stick(self, axis, value, port=0):
        self.send(f"stick {axis} {value} {port}" if port else f"stick {axis} {value}")

    def pause(self):
        return self.ask("pause", ("paused",), 2.0)[0] == "paused"

    def resume(self):
        self.send("resume")

    def quit(self, timeout=GAME_QUIT):
        """Ends it, its saves kept. (Waits for that, then makes sure.)"""
        p = self.p
        if p is None:
            return
        if p.poll() is None:
            self.send("quit")
            try:
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        try:
            p.stdin.close()
        except (OSError, ValueError):
            pass

    def alive(self):
        return self.p is not None and self.p.poll() is None and not self.ended
