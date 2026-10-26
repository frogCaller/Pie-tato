"""A game, in a process of its own: a libretro core (mGBA, Nestopia, Snes9x, PCSX ReARMed, Mupen64Plus, PPSSPP...)
runs it, and this draws its pictures straight onto the screen and plays its sound through aplay, a frame at a
time. A game drawn in 3D (an N64's, a PSP's) is drawn by the graphics chip, and each frame read back (pitato/gpu.py).
Media mode starts it (pitato/games.py) and tells it what to do, a line at a time:
    down a / up a        a button pressed, let go (a b x y l r l2 r2 start select up down left right)
    stick lx -64         where a stick is (lx ly: the left one, rx ry: the right), -127 to 127 (up and left
                         are minus)
    pause / resume       its menu is up: the game stops and draws nothing / on it goes
    save / load          its save state, made or put back
    reset                the game from the start
    keep                 in-game saves written now
    volume 80            how loud (0 to 100)
    picture Fit          as big as fits (Fit), whole pixels only (Sharp), or the whole screen (Fill: stretched to it)
    disc 2               another disc in (a game on more than one): the tray opens, then shuts a moment later
    peek 7 2037590:24    the game's memory, for an AI player (pitato/gameai.py): bytes at those addresses (hex,
                         as the game sees them), as many as asked (16 at most)
    mem /dev/shm/x       ...or all of its working memory (a Game Boy Advance's 32 KB and 256 KB), into that file
    shot /dev/shm/x      ...or its picture as it is on the screen now, about the size the game made it, into that
                         file (a PPM: an AI player shows it to its model)
    quit                 in-game saves and where you are kept, then it ends
It answers on a channel of its own (cores print what they like on its output): ready new|resumed,
disc 1 3 (the disc in, of how many), paused, resumed, saved, loaded, nostate, reset, error <why>, failed <why>
(the game ended itself as it started: a PSP game that won't boot), peek 7 <hex>... (- for memory it hasn't),
mem ok|none, shot ok|none, bye.

Run as: python3 -m pitato.emulator --core CORE --game GAME --saves FOLDER [--resume] ..."""
import argparse
import ctypes as C
import fcntl
import math
import os
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import zipfile
import zlib

import numpy as np

from .discs import cue_fixed
from .gpu import CORE_CB, GPU, GPUError, HWRender, ON_GPU, wanted_version
from .screen import fb_geometry, slow_pi

# libretro's numbers (libretro.h)
EXP = 0x10000
JOYPAD, ANALOG = 1, 5
MASK = 256
FMT_0RGB1555, FMT_XRGB8888, FMT_RGB565 = 0, 1, 2
SAVE_RAM, RTC = 0, 1
BUTTON_IDS = {"b": 0, "y": 1, "select": 2, "start": 3, "up": 4, "down": 5, "left": 6, "right": 7,
              "a": 8, "x": 9, "l": 10, "r": 11, "l2": 12, "r2": 13, "l3": 14, "r3": 15}
STICKS = {"lx": 0, "ly": 1, "rx": 2, "ry": 3}
PLAYERS = 4                                  # controllers a game can have, each a player of its own (media mode
                                             # says whose a press is: "down a 1" is player 2's A)
GAME_OPTIONS = {"mgba_sgb_borders": "OFF",      # a Game Boy game fills the screen: no Super Game Boy frame
                "pcsx_rearmed_memcard2": "none",   # one memory card, kept with the game's other saves
                # an N64 game: with R2 held, A B X Y are its C buttons, each where it is (A at the bottom is
                # C-Down, B on the right C-Right, X on the left C-Left, Y at the top C-Up). (pitato/screens/
                # games.py sends A and B as libretro's B and Y, the N64's A and B: C3 and C2 to it.) And one
                # thread, so its OpenGL is this one's.
                "mupen64plus-d-cbutton": "C3", "mupen64plus-r-cbutton": "C2",
                "mupen64plus-l-cbutton": "C4", "mupen64plus-u-cbutton": "C1",
                "mupen64plus-ThreadedRenderer": "False",
                # a DS game: both screens side by side (a TV's shape: pitato/screens/games.py's menu has the
                # others), the right stick moving a pointer on the touch screen and R3 touching it (R2, to you),
                # its pictures drawn on a thread of their own
                "melonds_screen_layout": "Left/Right", "melonds_touch_mode": "Joystick",
                "melonds_threaded_renderer": "enabled", "melonds_jit_enable": "enabled",
                "melonds_boot_directly": "enabled"}
LOG_ARGS = 6             # an emulator's printf (its log): what's after the format, read as whole numbers. (Where
                         # they are, as a function that takes them all would find them: in registers, then on
                         # the stack, on a Pi's 64-bit or 32-bit ARM and on a PC.) Only as many as the format
                         # says are used, and none of a format with fractions in it (they're elsewhere)
LOG = C.CFUNCTYPE(None, C.c_int, C.c_char_p, *([C.c_void_p] * LOG_ARGS))
LOG_SPEC = re.compile(r"%([-+ #0]*)(\*|\d+)?(?:\.(\*|\d*))?(hh|h|ll|l|j|z|t|q)?([diouxXcsp%])")
LOG_CORES = ("Mupen64Plus-Next", "ParaLLEl N64", "PPSSPP")   # emulators that crash with nowhere to log to
LOG_MOST = 200           # lines an emulator puts in the log, at most, a game (a PSP game can go on and on)
SWAP_FRAMES = 60         # frames the tray stays open when the disc's changed (so the game sees it)
RESUME_TRIES = 3         # frames run to pick up where you were, for an emulator that won't before it's running
LATE_STATES = ("Mupen64Plus-Next", "ParaLLEl N64")   # ...those emulators
SKIP_MOST = 3            # frames in a row left undrawn when it's behind, at most
SOUND_BUFFER = (80000, 20000)   # aplay's buffer and period (microseconds)
KEEP_EVERY = 10          # seconds between looks at the in-game save, to write it if it changed
LOG_EVERY = 30           # seconds between lines in the log on how it's keeping up
SLOW_WINDOW, SLOW_SHARE = 300, 0.2   # frames looked back on, and the share undrawn that's "slow"
BIG_SCREEN_MOST = 640 * 480 * 2   # pixels of picture, at most, on a big screen (a Pi Zero keeps up)
EARLY_END = 600          # frames: a game that ends itself sooner than this didn't really start (PPSSPP finds out
                         # a PSP game won't boot only once it's running)
PEEK_MOST = 16384        # bytes one peek reads, at most (an AI player's small look: where you are, a menu's cursor)
PEEK_RANGES = 16         # ...and places in one go, at most
SHOT_MOST = 640          # pixels across an AI player's picture of the game, at most (a 3D game's can be bigger)
PICTURES = ("Fit", "Sharp", "Fill")   # the picture's size: as big as fits, whole pixels only, the whole screen
MEM_REGIONS = ((0x03000000, 0x8000), (0x02000000, 0x40000))   # what mem writes: a GBA's working RAM (IWRAM, EWRAM)


def log_text(fmt, args):
    """An emulator's log line, its printf filled in from args (whole numbers: its arguments, as LOG reads them):
    text, %d, %x, %c, %p and so on. The format as it is when it can't be done safely (fractions, %n, something
    that takes two places)."""
    big = C.sizeof(C.c_void_p) * 8
    if re.search(r"%[-+ #0-9.*hljztqL]*[eEfFgGaAn]", fmt) or (big == 32 and re.search(r"%[-+ #0-9.*]*(ll|j|q)", fmt)):
        return fmt
    out, pos, k = [], 0, 0
    for m in LOG_SPEC.finditer(fmt):
        out.append(fmt[pos:m.start()])
        pos = m.end()
        flags, width, prec, size, conv = m.groups()
        if conv == "%":
            out.append("%")
            continue
        want = (width == "*") + (prec == "*") + 1
        if k + want > len(args):
            out.append(m.group(0))                       # (more than can be read: left as it is)
            continue
        got = [int(a or 0) for a in args[k:k + want]]
        k += want
        bits = big if size in ("l", "ll", "j", "z", "t", "q") or conv in "sp" else 32   # (a pointer: all of it)
        if width == "*":
            width = str(got.pop(0) & 0xFFFFFFFF)
        if prec == "*":
            prec = str(got.pop(0) & 0xFFFFFFFF)
        v = got[0] & ((1 << bits) - 1)
        if conv == "s":
            text, conv = (C.string_at(v).decode(errors="replace") if v else "(null)"), "s"
        elif conv == "c":
            text, conv = chr(v & 0xFF), "s"
        elif conv == "p":
            text, conv = hex(v), "s"
        elif conv in "di":
            text, conv = (v - (1 << bits) if v >> (bits - 1) else v), "d"
        else:
            text, conv = v, "d" if conv == "u" else conv
        spec = "%" + flags + (width or "") + ("." + prec if prec is not None else "") + conv
        try:
            out.append(spec % text)
        except (TypeError, ValueError):
            out.append(str(text))
    out.append(fmt[pos:])
    return "".join(out)


class SystemInfo(C.Structure):
    _fields_ = [("library_name", C.c_char_p), ("library_version", C.c_char_p),
                ("valid_extensions", C.c_char_p), ("need_fullpath", C.c_bool), ("block_extract", C.c_bool)]


class Geometry(C.Structure):
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float)]


class Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class Message(C.Structure):
    _fields_ = [("msg", C.c_char_p), ("frames", C.c_uint)]


class DiskControl(C.Structure):
    """The core's way to change discs (a PlayStation game on more than one)."""
    _fields_ = [("set_eject_state", C.CFUNCTYPE(C.c_bool, C.c_bool)), ("get_eject_state", C.CFUNCTYPE(C.c_bool)),
                ("get_image_index", C.CFUNCTYPE(C.c_uint)), ("set_image_index", C.CFUNCTYPE(C.c_bool, C.c_uint)),
                ("get_num_images", C.CFUNCTYPE(C.c_uint)),
                ("replace_image_index", C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)),
                ("add_image_index", C.CFUNCTYPE(C.c_bool))]


class MemoryDescriptor(C.Structure):
    """Where a piece of the game's memory is (libretro's retro_memory_descriptor)."""
    _fields_ = [("flags", C.c_uint64), ("ptr", C.c_void_p), ("offset", C.c_size_t), ("start", C.c_size_t),
                ("select", C.c_size_t), ("disconnect", C.c_size_t), ("len", C.c_size_t), ("addrspace", C.c_char_p)]


class MemoryMap(C.Structure):
    _fields_ = [("descriptors", C.POINTER(MemoryDescriptor)), ("num_descriptors", C.c_uint)]


class DiskControlExt(C.Structure):
    """...and the newer one, which can start the game on another disc."""
    _fields_ = DiskControl._fields_ + [
        ("set_initial_image", C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_char_p)),
        ("get_image_path", C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_char_p, C.c_size_t)),
        ("get_image_label", C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_char_p, C.c_size_t))]


ENVIRONMENT = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
SAMPLE = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
BATCH = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL = C.CFUNCTYPE(None)
STATE = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class GameError(Exception):
    """Why a game couldn't start, in words for the screen."""


def page_size():
    try:
        return os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        return 4096


SCRATCH = "pitato-game-"      # (in /tmp) a zipped game unzipped, or a .cue put right, while it plays


def scratch_dir():
    """A folder of the game's own while it plays. Any an emulator stopped short left behind go first."""
    tmp = tempfile.gettempdir()
    try:
        names = os.listdir(tmp)
    except OSError:
        names = []
    for n in names:
        m = re.match(re.escape(SCRATCH) + r"(\d+)-", n)
        if m and int(m.group(1)) != os.getpid():
            try:
                os.kill(int(m.group(1)), 0)            # (its emulator's still going: left alone)
                continue
            except ProcessLookupError:
                pass
            except OSError:
                continue
            shutil.rmtree(os.path.join(tmp, n), ignore_errors=True)
    return tempfile.mkdtemp(prefix=f"{SCRATCH}{os.getpid()}-")


def player(word):
    """A press's player (its controller's port), from media mode's word for it: 0 (player 1) unless it says."""
    try:
        port = int(word)
    except ValueError:
        return 0
    return port if 0 <= port < PLAYERS else 0


def game_data(path, exts):
    """(the game's bytes, in a buffer the emulator's given; how many; the name it goes by): a zip's first game
    inside it, if it's a zip. (A file's read straight into the buffer: a DS game can be hundreds of MB, so not
    twice over.)"""
    try:
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if os.path.splitext(info.filename)[1].lower() in exts and not info.is_dir():
                        data = z.read(info)
                        if info.filename.lower().endswith(".md") and b"\0" not in data[:512]:
                            continue                   # (a Markdown README, not a Mega Drive game)
                        return C.create_string_buffer(data, max(len(data), 1)), len(data), \
                            os.path.join(os.path.dirname(path), os.path.basename(info.filename))
            raise GameError("There's no game in that zip")
        with open(path, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            buf = C.create_string_buffer(max(size, 1))
            got = f.readinto((C.c_char * size).from_buffer(buf)) if size else 0
            if got != size:
                raise OSError("the file got shorter as it was read")
            return buf, size, path
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error, EOFError, ValueError) as ex:
        raise GameError("Couldn't read this game") from ex


def read_disc(path):
    """(the disc a game was on, counting from 0; its file) from its .disc file, or None."""
    try:
        with open(path, errors="replace") as f:
            lines = f.read().splitlines()
        return int(lines[0]), (lines[1] if len(lines) > 1 else "")
    except (OSError, ValueError, IndexError):
        return None


def write_file(path, data):
    """A save written whole or not at all, owned like its folder (this runs as root)."""
    folder = os.path.dirname(path)
    tmp = os.path.join(folder, "." + os.path.basename(path) + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        st = os.stat(folder)
        os.chown(tmp, st.st_uid, st.st_gid)
    except OSError:
        pass
    os.replace(tmp, path)


def picture_size(sw, sh, w, h, aspect, mode, most=None, whole=True):
    """(width, height) of a w x h picture on a sw x sh screen: as big as fits in its proper shape,
    whole pixels when that's nearly as big (crisper); or (Sharp) whole pixels only; or (Fill) the whole
    screen, stretched to it. `most` caps the pixels drawn (a Pi Zero on a TV). whole=False: as big as fits,
    always, in Fit (a picture the graphics chip smooths as it scales, an N64's or a PSP's, is no crisper in
    whole pixels: just smaller, with a black border round it on a TV)."""
    if mode == "Fill":
        k = math.sqrt(most / (sw * sh)) if most and sw * sh > most else 1.0
        return max(1, int(sw * k)), max(1, int(sh * k))
    if mode == "Sharp":
        k = max(1, min(sw // w, sh // h))
        while most and k > 1 and w * k * h * k > most:
            k -= 1
        return w * k, h * k
    ar = aspect if aspect and aspect > 0 else w / h
    dw, dh = float(sw), sw / ar
    if dh > sh:
        dw, dh = sh * ar, float(sh)
    if most and dw * dh > most:
        k = math.sqrt(most / (dw * dh))
        dw, dh = dw * k, dh * k
    k = int(dh // h)
    if whole and k >= 1 and k * h / dh >= 0.88:
        dw, dh = k * h * ar, float(k * h)
    return max(1, min(sw, int(round(dw)))), max(1, min(sh, int(round(dh))))


class Screen:
    """The framebuffer, written a band of rows at a time: the picture in the middle, black either side."""

    def __init__(self, dev="/dev/fb0"):
        test = os.environ.get("PITATO_FB")         # (the tests: path:WxH:bits, a plain file)
        if test:
            path, size, bits = test.rsplit(":", 2)
            w, h = (int(v) for v in size.split("x"))
            bpp = int(bits)
            fields = [(11, 5), (5, 6), (0, 5)] if bpp == 16 else [(16, 8), (8, 8), (0, 8)]
            self.f = open(path, "r+b", buffering=0)
            geo = (w, h, 0, 0, bpp, fields, w * bpp // 8)
        else:
            self.f = open(dev, "r+b", buffering=0)
            geo = fb_geometry(self.f)
        self.w, self.h, self.xo, self.yo, self.bpp, fields, self.stride = geo
        if self.bpp not in (16, 32):
            raise OSError(f"unsupported framebuffer depth {self.bpp}")
        self.fields = [tuple(f) for f in fields]
        self.dtype = np.dtype("<u2" if self.bpp == 16 else "<u4")
        self.row_px = self.stride // (self.bpp // 8)
        self.most = BIG_SCREEN_MOST if (self.w, self.h) != (640, 480) and slow_pi() else None
        self.luts = {}
        self.plan = None                              # what the last picture's layout was for
        self.mode = "Fit"

    def native(self, fmt):
        """The core's pixels go straight onto the screen."""
        return ((fmt == FMT_RGB565 and self.bpp == 16 and self.fields == [(11, 5), (5, 6), (0, 5)])
                or (fmt == FMT_XRGB8888 and self.bpp == 32 and self.fields[:3] == [(16, 8), (8, 8), (0, 8)]))

    def pack(self, r, g, b):
        """8-bit red, green, blue as the screen's pixels."""
        out = np.zeros(np.shape(r), dtype=np.uint32)
        for v, (off, ln) in zip((r, g, b), self.fields):
            out |= (np.asarray(v, dtype=np.uint32) >> (8 - ln)) << off
        return out.astype(self.dtype)

    def convert(self, a, fmt):
        """A frame (the core's pixels) as the screen's."""
        if self.native(fmt):
            return a
        if fmt == FMT_XRGB8888:
            a = a.astype(np.uint32)
            if self.bpp == 16 and self.fields == [(11, 5), (5, 6), (0, 5)]:
                return (((a >> 8) & 0xF800) | ((a >> 5) & 0x07E0) | ((a >> 3) & 0x001F)).astype(self.dtype)
            return self.pack((a >> 16) & 255, (a >> 8) & 255, a & 255)
        lut = self.luts.get(fmt)
        if lut is None:                               # 16-bit pixels: a table of all 65536
            p = np.arange(65536, dtype=np.uint32)
            if fmt == FMT_RGB565:
                r, g, b = (p >> 11) & 31, (p >> 5) & 63, p & 31
                lut = self.pack((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))
            else:
                r, g, b = (p >> 10) & 31, (p >> 5) & 31, p & 31
                lut = self.pack((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2))
            self.luts[fmt] = lut
        return lut[a]

    def layout(self, w, h, aspect, whole=True):
        key = (w, h, round(aspect or 0, 4), self.mode, whole)
        if self.plan and self.plan[0] == key:
            return self.plan
        dw, dh = picture_size(self.w, self.h, w, h, aspect, self.mode, self.most, whole)
        x0, y0 = (self.w - dw) // 2, (self.h - dh) // 2
        ys = (np.arange(dh) * h // dh).astype(np.intp)
        xs = (np.arange(dw) * w // dw).astype(np.intp)
        band = np.zeros((dh, self.row_px), dtype=self.dtype)
        view = band[:, self.xo + x0:self.xo + x0 + dw]
        cols = np.empty((h, dw), dtype=self.dtype)
        if self.plan is not None:
            self.clear()                              # (a new size: no bits of the old one left)
        self.plan = (key, ys, xs, band, view, (y0 + self.yo) * self.stride, cols)
        return self.plan

    def show(self, a, fmt, aspect):
        """A frame onto the screen: wider first (fewer rows), then taller, then the rows written at once."""
        h, w = a.shape
        _, ys, xs, band, view, at, cols = self.layout(w, h, aspect)
        np.take(self.convert(a, fmt), xs, axis=1, out=cols, mode="clip")
        np.take(cols, ys, axis=0, out=view, mode="clip")
        os.pwrite(self.f.fileno(), band, at)

    def show_gpu(self, gpu, w, h, aspect, flipped=True):
        """A frame the graphics chip drew (a 3D game's, w x h): the chip makes it the picture's size and reads
        it into the rows, in the screen's own pixels when it can. In Fit, as big as fits: the chip smooths it as
        it scales, so whole pixels wouldn't make it any crisper."""
        _, _, _, band, view, at, _ = self.layout(w, h, aspect, whole=False)
        kind = "rgb565" if self.native(FMT_RGB565) else "xrgb8888" if self.native(FMT_XRGB8888) else None
        got = gpu.read(view, kind, self.row_px, w, h, flipped, smooth=self.mode != "Sharp")
        if got is not None:                           # (red, green, blue bytes: the screen's pixels made here)
            view[...] = self.pack(got[..., 0], got[..., 1], got[..., 2])
        os.pwrite(self.f.fileno(), band, at)

    def clear(self):
        os.pwrite(self.f.fileno(), bytes(self.stride * self.h), self.yo * self.stride)

    def shot(self, path, most=SHOT_MOST):
        """The game's last picture, as it is on the screen (not the black either side), one of the screen's
        pixels for each of the game's own (smaller if it's still more than `most` across), into a PPM file.
        False before it's drawn one. (A quick copy out of the rows the screen was given, between frames.)"""
        if self.plan is None:
            return False
        key, ys, xs, _, view, _, _ = self.plan
        w, h = key[0], key[1]
        rows = np.unique(np.searchsorted(ys, np.arange(h)).clip(0, len(ys) - 1))
        cols = np.unique(np.searchsorted(xs, np.arange(w)).clip(0, len(xs) - 1))
        step = max(1, -(-len(cols) // most))
        a = view[rows[::step]][:, cols[::step]].astype(np.uint32)
        rgb = np.stack([((a >> off) & ((1 << ln) - 1)) << (8 - ln) for off, ln in self.fields[:3]], -1)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(b"P6\n%d %d\n255\n" % (a.shape[1], a.shape[0]))
            f.write(rgb.astype(np.uint8).tobytes())
        os.replace(tmp, path)
        return True

    def snapshot(self, max_w=640):
        """What's on the screen now, as a picture at most max_w wide (a game's menu goes over it)."""
        from PIL import Image
        data = os.pread(self.f.fileno(), self.stride * self.h, self.yo * self.stride)
        a = np.frombuffer(data, dtype=self.dtype).reshape(self.h, self.row_px)[:, self.xo:self.xo + self.w]
        step = max(1, -(-self.w // max_w))
        a = a[::step, ::step].astype(np.uint32)
        rgb = [((a >> off) & ((1 << ln) - 1)) << (8 - ln) for off, ln in self.fields[:3]]
        return Image.fromarray(np.stack(rgb, -1).astype(np.uint8), "RGB")

    def close(self):
        self.f.close()


def screen_picture(dev="/dev/fb0", max_w=640):
    """The screen as it is (a game's last picture), or None."""
    try:
        s = Screen(dev)
    except (OSError, ValueError):
        return None
    try:
        return s.snapshot(max_w)
    except (OSError, ValueError):
        return None
    finally:
        s.close()


class Sound:
    """aplay, fed through a pipe a frame at a time. How full the pipe is says whether the game runs a
    touch quick or slow for the speaker, and the frames are timed a hair longer or shorter to match."""
    PIPE = 16384

    def __init__(self, device, rate, volume):
        self.device, self.rate, self.volume = device, int(round(rate)), volume
        self.p = self.fd = None
        self.frame_bytes = 4 * self.rate // 60
        self.target = min(self.PIPE // 2, self.frame_bytes * 3 // 2)
        self.dropped = 0

    def start(self):
        if self.p is not None or self.rate <= 0:
            return
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", "2", "-r", str(self.rate),
               f"--buffer-time={SOUND_BUFFER[0]}", f"--period-time={SOUND_BUFFER[1]}"]
        if self.device:
            cmd += ["-D", self.device]
        try:
            self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, bufsize=0)
        except OSError as ex:
            print(f"game: no sound ({ex})", file=sys.stderr, flush=True)
            self.p = None
            return
        self.fd = self.p.stdin.fileno()
        try:
            fcntl.fcntl(self.fd, fcntl.F_SETPIPE_SZ, self.PIPE)
        except (OSError, AttributeError):
            pass
        os.set_blocking(self.fd, False)
        self.write(bytes(self.target), raw=True)      # a little silence to start, so it never runs dry

    def stop(self):
        p, self.p = self.p, None
        if p is not None:
            try:
                p.stdin.close()
            except OSError:
                pass
            try:
                p.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()

    def write(self, data, raw=False):
        if self.p is None or not data:
            return
        if not raw and self.volume < 100:
            a = np.frombuffer(data, dtype="<i2")
            data = ((a.astype(np.int32) * int(self.volume * 256 // 100)) >> 8).astype("<i2").tobytes() \
                if self.volume > 0 else bytes(len(data))
        for i in range(0, len(data), 4096):           # (pieces no bigger than a pipe writes whole)
            try:
                os.write(self.fd, data[i:i + 4096])
            except BlockingIOError:
                self.dropped += 1
                return
            except (BrokenPipeError, OSError):
                print("game: the sound stopped", file=sys.stderr, flush=True)
                self.p = None
                return

    def fill(self):
        try:
            return struct.unpack("i", fcntl.ioctl(self.fd, termios.FIONREAD, b"\0\0\0\0"))[0]
        except (OSError, TypeError):
            return None

    def drift(self):
        """How much longer (+) or shorter (-) the next frame should be, as a fraction of a frame."""
        if self.p is None:
            return 0.0
        n = self.fill()
        if n is None:
            return 0.0
        err = max(-1.0, min(1.0, (n - self.target) / self.target))
        return err * 0.005


class Core:
    """A libretro core, and the game it's playing."""

    def __init__(self, path, game, exts, saves, name, system_dir, on_video, first_disc=None, options=None):
        self.lib = C.CDLL(path)
        self.path = path
        self.options = dict(options or {})            # its settings as asked for (over GAME_OPTIONS)
        self.options_changed = False                   # ...one changed while it plays: it's told
        if page_size() != 4096:                        # (a Pi 5's 16 KB pages: melonDS's quick memory needs 4 KB)
            self.options.setdefault("melonds_jit_fast_memory", "disabled")
        self.fmt = FMT_0RGB1555
        self.av = AVInfo()
        self.defaults, self.held_strings = {}, {}
        self.draw = True
        self.quit = False
        self.on_video = on_video
        self.audio = bytearray()
        self.buttons = [0] * PLAYERS                   # each player's
        self.sticks = [[0, 0, 0, 0] for _ in range(PLAYERS)]   # ...left x, y, right x, y: -32767 to 32767
        self.ports = {0}                               # the players whose controllers it's been told are there
        self.gpu, self.hw, self.gpu_error = None, None, ""   # (a game drawn in 3D: the graphics chip)
        self.log_cb = LOG(self.log)
        self.logged = 0                                # (lines it's put in the log)
        self.disk, self.disk_ext = None, False         # (a game on discs: changing them)
        self.regions = []                              # its memory, where the game sees it: (start, length, pointer)
        self.saves, self.name = saves, name
        self.system_dir = system_dir.encode()
        self.saves_b = saves.encode()
        self.path_b = path.encode()
        L = self.lib
        for fn, res, args in (("retro_api_version", C.c_uint, []), ("retro_init", None, []),
                              ("retro_deinit", None, []), ("retro_run", None, []), ("retro_reset", None, []),
                              ("retro_unload_game", None, []), ("retro_serialize_size", C.c_size_t, []),
                              ("retro_serialize", C.c_bool, [C.c_void_p, C.c_size_t]),
                              ("retro_unserialize", C.c_bool, [C.c_void_p, C.c_size_t]),
                              ("retro_get_memory_data", C.c_void_p, [C.c_uint]),
                              ("retro_get_memory_size", C.c_size_t, [C.c_uint]),
                              ("retro_load_game", C.c_bool, [C.POINTER(GameInfo)]),
                              ("retro_get_system_info", None, [C.POINTER(SystemInfo)]),
                              ("retro_get_system_av_info", None, [C.POINTER(AVInfo)]),
                              ("retro_set_controller_port_device", None, [C.c_uint, C.c_uint])):
            f = getattr(L, fn)
            f.restype, f.argtypes = res, args
        if L.retro_api_version() != 1:
            raise GameError("That emulator is too new or too old for this")
        info = SystemInfo()
        L.retro_get_system_info(C.byref(info))         # (asked before it starts: libretro allows that)
        self.library = (info.library_name or b"").decode(errors="replace")
        self.scratch = None                            # (a zipped game unzipped, a .cue put right: while it plays)
        if info.need_fullpath:                         # a disc (or a Genesis game): the emulator reads it from its file
            kinds = [k for k in (info.valid_extensions or b"").decode(errors="replace").lower().split("|") if k]
            ext = os.path.splitext(game)[1].lower().lstrip(".")
            if ext == "zip" and set(exts) & {".cue", ".iso", ".chd", ".pbp", ".cso", ".m3u"}:   # (a disc's, zipped)
                raise GameError("Unzip this game to play it")
            try:
                if ext == "zip":                       # a cartridge's, zipped: out of it while it plays
                    buf, size, inside = game_data(game, exts)
                    self.scratch = scratch_dir()
                    game = os.path.join(self.scratch, os.path.basename(inside))
                    with open(game, "wb") as f:
                        f.write(C.string_at(buf, size))
                    del buf
                    ext = os.path.splitext(game)[1].lower().lstrip(".")
                if kinds and ext not in kinds:
                    raise GameError(f"This emulator can't play .{ext} files")
                if ext == "cue":
                    self.scratch = self.scratch or scratch_dir()
                    game = cue_fixed(game, self.scratch)
            except BaseException:
                if self.scratch:                       # (nothing left behind)
                    shutil.rmtree(self.scratch, ignore_errors=True)
                    self.scratch = None
                raise
            self.data, size = None, 0
            self.game_path = os.path.abspath(game).encode()
        else:
            self.data, size, fake_path = game_data(game, exts)   # (kept until the game's unloaded)
            self.game_path = fake_path.encode()
        self.callbacks = [ENVIRONMENT(self.environment), VIDEO(self.video), SAMPLE(self.sample),
                          BATCH(self.batch), POLL(self.poll), STATE(self.state)]
        for fn, cb in zip(("retro_set_environment", "retro_set_video_refresh", "retro_set_audio_sample",
                           "retro_set_audio_sample_batch", "retro_set_input_poll", "retro_set_input_state"),
                          self.callbacks):
            getattr(L, fn)(cb)
        L.retro_init()
        if first_disc and first_disc[1] and self.disk_ext and self.disk.set_initial_image:
            self.disk.set_initial_image(first_disc[0], first_disc[1].encode())   # (the disc you were on)
        gi = GameInfo(self.game_path, C.cast(self.data, C.c_void_p) if self.data is not None else None, size, None)
        self.game_info = gi                            # (kept while it plays: melonDS reads it again to start over)
        if not L.retro_load_game(C.byref(gi)):
            L.retro_deinit()
            self.close_gpu()
            if self.scratch:
                shutil.rmtree(self.scratch, ignore_errors=True)
            raise GameError(self.gpu_error or "This game didn't load")
        L.retro_set_controller_port_device(0, JOYPAD)
        L.retro_get_system_av_info(C.byref(self.av))
        self.loaded = True
        if self.hw is not None:
            self.start_3d()

    def start_3d(self):
        """A game the graphics chip draws: its framebuffer, as big as its biggest picture, then the
        emulator's told its OpenGL is ready (it sets itself up in it)."""
        g = self.av.geometry
        try:
            self.gpu.framebuffer(max(g.max_width, g.base_width, 1), max(g.max_height, g.base_height, 1),
                                 self.hw["depth"], self.hw["stencil"])
        except GPUError as ex:
            self.close()
            raise GameError(str(ex)) from ex
        self.hw["live"] = True
        if self.hw["reset"]:
            CORE_CB(self.hw["reset"])()

    # -- what the core asks of us ------------------------------------------------
    def environment(self, cmd, data):
        try:
            return self.answer(cmd, data)
        except Exception as ex:
            print(f"game: environment {cmd}: {ex!r}", file=sys.stderr, flush=True)
            return False

    def put_string(self, data, value):
        C.cast(data, C.POINTER(C.c_char_p))[0] = value

    def answer(self, cmd, data):
        if cmd == 10:                                 # SET_PIXEL_FORMAT
            fmt = C.cast(data, C.POINTER(C.c_int))[0]
            if fmt in (FMT_0RGB1555, FMT_XRGB8888, FMT_RGB565):
                self.fmt = fmt
                return True
            return False
        if cmd == 3:                                  # GET_CAN_DUPE
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd in (9, 30):                            # GET_SYSTEM_DIRECTORY, GET_CORE_ASSETS_DIRECTORY
            self.put_string(data, self.system_dir)
            return True
        if cmd == 31:                                 # GET_SAVE_DIRECTORY
            self.put_string(data, self.saves_b)
            return True
        if cmd == 19:                                 # GET_LIBRETRO_PATH
            self.put_string(data, self.path_b)
            return True
        if cmd == 16:                                 # SET_VARIABLES: each one's first choice is its default
            p = C.cast(data, C.POINTER(Variable))
            i = 0
            while p[i].key:
                desc = (p[i].value or b"").decode(errors="replace")
                self.defaults[p[i].key.decode()] = desc.split("; ", 1)[-1].split("|")[0]
                i += 1
            return True
        if cmd == 15:                                 # GET_VARIABLE
            v = C.cast(data, C.POINTER(Variable))[0]
            key = (v.key or b"").decode()
            val = self.options.get(key, GAME_OPTIONS.get(key, self.defaults.get(key)))
            if val is None:
                v.value = None
                return False
            b = self.held_strings.setdefault(key + "=" + val, val.encode())
            v.value = b
            return True
        if cmd == 17:                                 # GET_VARIABLE_UPDATE: a setting changed (once)
            C.cast(data, C.POINTER(C.c_bool))[0] = self.options_changed
            self.options_changed = False
            return True
        if cmd == (47 | EXP):                         # GET_AUDIO_VIDEO_ENABLE: no picture when behind
            if data:
                C.cast(data, C.POINTER(C.c_int))[0] = 3 if self.draw else 2
            return True
        if cmd == (51 | EXP):                         # GET_INPUT_BITMASKS
            return True
        if cmd == 39:                                 # GET_LANGUAGE: English
            C.cast(data, C.POINTER(C.c_uint))[0] = 0
            return True
        if cmd == 24:                                 # GET_INPUT_DEVICE_CAPABILITIES
            C.cast(data, C.POINTER(C.c_uint64))[0] = 1 << JOYPAD
            return True
        if cmd == 14:                                 # SET_HW_RENDER: it draws with the graphics chip
            return self.hw_render(data)
        if cmd == 27 and self.library in LOG_CORES:   # GET_LOG_INTERFACE
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(self.log_cb, C.c_void_p).value
            return True
        if cmd == 61:                                 # GET_INPUT_MAX_USERS
            C.cast(data, C.POINTER(C.c_uint))[0] = PLAYERS
            return True
        if cmd == (49 | EXP):                         # GET_FASTFORWARDING
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == (50 | EXP):                         # GET_TARGET_REFRESH_RATE
            C.cast(data, C.POINTER(C.c_float))[0] = self.av.timing.fps or 60.0
            return True
        if cmd == 32:                                 # SET_SYSTEM_AV_INFO
            self.av = AVInfo.from_buffer_copy(C.string_at(data, C.sizeof(AVInfo)))
            return True
        if cmd == 37:                                 # SET_GEOMETRY
            self.av.geometry = Geometry.from_buffer_copy(C.string_at(data, C.sizeof(Geometry)))
            return True
        if cmd == 7:                                  # SHUTDOWN
            self.quit = True
            return True
        if cmd == 57:                                 # GET_DISK_CONTROL_INTERFACE_VERSION: the newer one
            C.cast(data, C.POINTER(C.c_uint))[0] = 1
            return True
        if cmd in (13, 58):                           # SET_DISK_CONTROL_(EXT_)INTERFACE: how discs change
            if not data:                              # (none after all: Genesis Plus GX, for a cartridge's game)
                self.disk, self.disk_ext = None, False
                return True
            kind = DiskControlExt if cmd == 58 else DiskControl
            self.disk = kind.from_buffer_copy(C.string_at(data, C.sizeof(kind)))
            self.disk_ext = cmd == 58
            return True
        if cmd == 6:                                  # SET_MESSAGE: into the log
            m = C.cast(data, C.POINTER(Message))[0]
            if m.msg:
                print(f"game: the emulator says {m.msg.decode(errors='replace')!r}", file=sys.stderr, flush=True)
            return True
        if cmd == (36 | EXP):                         # SET_MEMORY_MAPS: where its memory is (an AI player reads it)
            m = C.cast(data, C.POINTER(MemoryMap))[0]
            self.regions = [(d.start, d.len, d.ptr + d.offset)
                            for d in (m.descriptors[i] for i in range(m.num_descriptors)) if d.ptr and d.len]
            return True
        if cmd in (8, 11, 34, 35, 42 | EXP, 44, 55, 60, 63):
            return True                               # (told, and nothing to do about it)
        return False

    def hw_render(self, data):
        """It draws with the graphics chip (OpenGL ES): the context is made now (so it knows there's one),
        its framebuffer once the game has loaded."""
        hw = C.cast(data, C.POINTER(HWRender)).contents
        version = wanted_version(hw)
        if version is None:
            self.gpu_error = "That emulator wants graphics this can't give it"
            return False
        if self.gpu is None:
            try:
                self.gpu = GPU(version)
            except GPUError as ex:
                self.gpu_error = str(ex)
                return False
        self.gpu.hand_over(hw)
        self.hw = {"reset": hw.context_reset, "destroy": hw.context_destroy, "depth": bool(hw.depth),
                   "stencil": bool(hw.stencil), "flipped": bool(hw.bottom_left_origin), "live": False}
        return True

    def log(self, level, fmt, *args):
        """What the emulator says: its warnings and errors (2, 3) into the log, its chatter (0, 1) not. (From
        any of its threads: a PSP emulator's runs the game on one of its own.)"""
        if level < 2 or not fmt or self.logged > LOG_MOST:
            return
        self.logged += 1
        try:
            text = log_text(fmt.decode(errors="replace"), args).strip()
        except Exception:                             # (it mustn't take the game down)
            text = fmt.decode(errors="replace").strip()
        if self.logged > LOG_MOST:
            text = "... (and more: no more of it)"
        print(f"game: the emulator says {text!r}", file=sys.stderr, flush=True)

    def video(self, data, w, h, pitch):
        if not data or not self.draw:
            return
        if data == ON_GPU:                            # drawn by the graphics chip, and still in it
            if self.gpu is not None:
                self.on_video(None, (w, h), self.av.geometry.aspect_ratio)
            return
        bpp = 4 if self.fmt == FMT_XRGB8888 else 2
        buf = (C.c_uint8 * (pitch * h)).from_address(data)
        a = np.frombuffer(buf, dtype=np.uint32 if bpp == 4 else np.uint16).reshape(h, pitch // bpp)[:, :w]
        self.on_video(a, self.fmt, self.av.geometry.aspect_ratio)

    def sample(self, left, right):
        self.audio += struct.pack("<hh", left, right)

    def batch(self, data, frames):
        if data and frames:
            self.audio += C.string_at(data, frames * 4)
        return frames

    def poll(self):
        pass

    def state(self, port, device, index, id_):
        if port >= PLAYERS:
            return 0
        kind = device & 0xFF
        if kind == JOYPAD:
            held = self.buttons[port]
            if id_ == MASK:
                return held
            return (held >> id_) & 1 if id_ < 16 else 0
        if kind == ANALOG and index < 2 and id_ < 2:   # a stick (0 the left, 1 the right): x or y
            return self.sticks[port][index * 2 + id_]
        return 0

    def plug(self, port):
        """A player's controller, there from now on (as the first thing they press happens): player 2's, say."""
        if port not in self.ports and 0 <= port < PLAYERS:
            self.ports.add(port)
            self.lib.retro_set_controller_port_device(port, JOYPAD)

    # -- the game ------------------------------------------------------------------
    def run(self):
        self.lib.retro_run()

    def memory(self, kind):
        size = self.lib.retro_get_memory_size(kind)
        ptr = self.lib.retro_get_memory_data(kind)
        return (ptr, size) if ptr and size else (None, 0)

    def read_memory(self, kind):
        ptr, size = self.memory(kind)
        return C.string_at(ptr, size) if ptr else b""

    def peek(self, addr, n):
        """n bytes of the game's memory at addr, as the game sees it (None: it hasn't that memory)."""
        for start, length, ptr in self.regions:
            if start <= addr and addr + n <= start + length:
                return C.string_at(ptr + addr - start, n)
        return None

    def dump(self, path):
        """Its working memory (MEM_REGIONS, one after the other) into a file, whole: False if it hasn't it."""
        parts = [self.peek(start, n) for start, n in MEM_REGIONS]
        if any(p is None for p in parts):
            return False
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            for p in parts:
                f.write(p)
        os.replace(tmp, path)
        return True

    def put_memory(self, kind, data):
        ptr, size = self.memory(kind)
        if ptr and data:
            C.memmove(ptr, data, min(size, len(data)))
            return True
        return False

    def serialize(self):
        size = self.lib.retro_serialize_size()
        if not size:
            return None
        buf = C.create_string_buffer(size)
        return buf.raw if self.lib.retro_serialize(buf, size) else None

    def unserialize(self, data):
        buf = C.create_string_buffer(data, len(data))
        return bool(self.lib.retro_unserialize(buf, len(data)))

    # -- discs (a game on more than one) --------------------------------------------------
    def discs(self):
        """(the disc in, counting from 0; how many there are): (0, 1) for a game on one."""
        d = self.disk
        if d is None or not d.get_num_images:
            return 0, 1
        n = int(d.get_num_images())
        i = int(d.get_image_index()) if d.get_image_index else 0
        return (min(max(i, 0), n - 1), n) if n > 0 else (0, 1)

    def disc_path(self, index):
        """The file a disc's in, as the emulator knows it ('' if it can't say)."""
        d = self.disk
        if d is None or not self.disk_ext or not d.get_image_path:
            return ""
        buf = C.create_string_buffer(4096)
        return buf.value.decode(errors="replace") if d.get_image_path(index, buf, len(buf)) else ""

    def swap(self, index, close=False):
        """Another disc: the tray opens and in it goes (the tray shut again too, if close). False: no such disc."""
        d = self.disk
        i, n = self.discs()
        if d is None or not (0 <= index < n) or index == i or not (d.set_eject_state and d.set_image_index):
            return False
        d.set_eject_state(True)
        ok = bool(d.set_image_index(index))
        if close:
            d.set_eject_state(False)
        return ok

    def shut_tray(self):
        if self.disk is not None and self.disk.set_eject_state:
            self.disk.set_eject_state(False)

    def close(self):
        if self.loaded:
            self.loaded = False
            self.end_3d()                             # (first, as RetroArch does: PPSSPP counts on it)
            self.lib.retro_unload_game()
            self.lib.retro_deinit()
        self.close_gpu()
        if self.scratch:
            shutil.rmtree(self.scratch, ignore_errors=True)
            self.scratch = None

    def end_3d(self):
        """The emulator told its OpenGL is going (once, and only if it was handed it), while it's still there."""
        if self.gpu is not None and self.hw and self.hw["live"]:
            self.hw["live"] = False
            if self.hw["destroy"]:
                CORE_CB(self.hw["destroy"])()

    def close_gpu(self):
        """The graphics chip let go (the emulator told first, if it hasn't been)."""
        self.end_3d()
        gpu, self.gpu = self.gpu, None
        if gpu is not None:
            gpu.close()


class Session:
    """One game, from starting up to quitting: the core, the screen, the sound, the buttons, the saves."""

    def __init__(self, args, chan):
        self.args, self.chan = args, chan
        self.quit = False
        self.paused = False
        self.closed = False
        self.frame = 0
        self.beat = time.monotonic()                  # when the next frame is due
        self.down_at = {}                             # (player, button) -> the frame it went down
        self.letgo = {}                               # (player, button) -> the frame it goes up (a quick tap)
        self.inbuf = b""
        self.saved_sram = None
        self.next_keep = time.monotonic() + KEEP_EVERY
        self.stats = [0, 0, 0.0, 0.0, time.monotonic()]   # frames, not drawn, emulator secs, picture secs, since
        self.recent = [[0, 0], [0, 0]]                # (frames, not drawn): the window before, and this one
        try:
            if not os.path.isdir(args.saves):
                os.makedirs(args.saves, exist_ok=True)
                parent = os.stat(os.path.dirname(os.path.abspath(args.saves)))
                os.chown(args.saves, parent.st_uid, parent.st_gid)   # (yours, like the Games folder)
        except OSError as ex:
            print(f"game: no saves folder ({ex})", file=sys.stderr, flush=True)
        self.base = os.path.join(args.saves, args.name)
        self.insert_at = None                         # the frame a changed disc's tray shuts
        self.first_disc = None                        # the disc it was on, when it picks up where you left off
        if args.resume and os.path.isfile(self.base + ".state.auto"):
            self.first_disc = read_disc(self.base + ".disc")
        try:
            self.screen = Screen(args.fb)
        except OSError as ex:
            raise GameError("Couldn't draw on the screen") from ex
        self.screen.mode = args.picture
        exts = tuple(e.lower() for e in args.exts.split(","))
        try:
            self.core = Core(args.core, args.game, exts, args.saves, args.name, args.system, self.picture,
                             first_disc=self.first_disc,
                             options=dict(o.split("=", 1) for o in (args.option or []) if "=" in o))
        except OSError as ex:
            self.screen.close()
            raise GameError("Couldn't start the emulator") from ex
        except GameError:
            self.screen.close()
            raise
        self.sound = Sound(args.sound, self.core.av.timing.sample_rate, args.volume)

    def slow(self):
        """It's been behind (frames left undrawn) a good share of the last few hundred frames."""
        n = self.recent[0][0] + self.recent[1][0]
        return n >= 60 and (self.recent[0][1] + self.recent[1][1]) / n > SLOW_SHARE

    def say(self, *words):
        try:
            self.chan.write(" ".join(str(w) for w in words) + "\n")
        except (OSError, ValueError):
            self.quit = True                          # media mode has gone: end, keeping things

    # -- the pictures ------------------------------------------------------------------
    def picture(self, a, fmt, aspect):
        t = time.perf_counter()
        if a is None:                                 # (a 3D game's: the chip has it, fmt is its size)
            self.screen.show_gpu(self.core.gpu, fmt[0], fmt[1], aspect, self.core.hw["flipped"])
        else:
            self.screen.show(a, fmt, aspect)
        self.stats[3] += time.perf_counter() - t

    # -- saves -------------------------------------------------------------------------
    def load_saves(self):
        """The in-game save: this game's, or (the first time) one from another emulator next to it."""
        game_dir, stem = os.path.dirname(self.args.game), os.path.splitext(os.path.basename(self.args.game))[0]
        for kind, ext, also in ((SAVE_RAM, ".srm", (".srm", ".sav", ".mcr", ".mcd")), (RTC, ".rtc", (".rtc",))):
            for path in [self.base + ext] + [os.path.join(game_dir, stem + e) for e in also]:
                if os.path.isfile(path):
                    try:
                        with open(path, "rb") as f:
                            self.core.put_memory(kind, f.read())
                    except OSError:
                        continue
                    break
        self.saved_sram = self.core.read_memory(SAVE_RAM) + self.core.read_memory(RTC)

    def keep(self):
        """The in-game save (and the clock some games keep), written if it changed."""
        sram, rtc = self.core.read_memory(SAVE_RAM), self.core.read_memory(RTC)
        if sram + rtc == self.saved_sram:
            return
        try:
            if sram:
                write_file(self.base + ".srm", sram)
            if rtc:
                write_file(self.base + ".rtc", rtc)
            self.saved_sram = sram + rtc
        except OSError as ex:
            print(f"game: couldn't write its save ({ex})", file=sys.stderr, flush=True)

    def keep_disc(self):
        """Which disc it's on (a game on more than one), for next time."""
        i, n = self.core.discs()
        path = self.base + ".disc"
        try:
            if n > 1:
                write_file(path, f"{i}\n{self.core.disc_path(i)}\n".encode())
            elif os.path.exists(path):
                os.remove(path)
        except OSError as ex:
            print(f"game: couldn't note its disc ({ex})", file=sys.stderr, flush=True)

    def save_state(self, ext):
        data = self.core.serialize()
        if data is None:
            return False
        try:
            write_file(self.base + ext, data)
            return True
        except OSError as ex:
            print(f"game: couldn't save its state ({ex})", file=sys.stderr, flush=True)
            return False

    def load_state(self, ext):
        """True: put back; False: it wouldn't go; None: there isn't one."""
        try:
            with open(self.base + ext, "rb") as f:
                data = f.read()
        except OSError:
            return None
        return self.core.unserialize(data)

    # -- what media mode says -------------------------------------------------------------
    def commands(self, wait):
        """Lines from media mode: whatever's there, waiting up to `wait` seconds for some."""
        try:
            ready, _, _ = select.select([0], [], [], max(0.0, wait))
        except (OSError, ValueError):
            ready = []
        if not ready:
            return
        try:
            data = os.read(0, 4096)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self.quit = True                          # media mode has gone: end, keeping things
            return
        self.inbuf += data
        while b"\n" in self.inbuf and not self.quit:
            line, self.inbuf = self.inbuf.split(b"\n", 1)
            self.command(line.decode(errors="replace").split())

    def command(self, words):
        if not words:
            return
        what, arg = words[0], (words[1] if len(words) > 1 else "")
        bit = BUTTON_IDS.get(arg)
        if what in ("down", "up") and bit is not None:
            port = player(words[2] if len(words) > 2 else "")    # (whose: player 1's, unless it says)
            key = (port, arg)
            if what == "down":
                if not self.paused:
                    self.core.plug(port)
                    self.core.buttons[port] |= 1 << bit
                    self.down_at[key] = self.frame
                    self.letgo.pop(key, None)
            elif self.frame - self.down_at.get(key, -99) < 2:
                self.letgo[key] = self.down_at[key] + 2   # a tap: down two frames, so the game sees it
            else:
                self.core.buttons[port] &= ~(1 << bit)
        elif what == "stick" and arg in STICKS:
            try:
                v = max(-127, min(127, int(words[2])))
            except (IndexError, ValueError):
                return
            port = player(words[3] if len(words) > 3 else "")
            if not self.paused:
                self.core.plug(port)
                self.core.sticks[port][STICKS[arg]] = int(v * 32767 / 127)
        elif what == "pause":
            if not self.paused:
                self.paused = True
                self.core.buttons = [0] * PLAYERS
                self.core.sticks = [[0, 0, 0, 0] for _ in range(PLAYERS)]
                self.letgo.clear()
                self.sound.stop()
                self.keep()
            self.say("paused", "slow" if self.slow() else "ok")
        elif what == "resume":
            if self.paused:
                self.paused = False
                self.screen.clear()
                self.sound.start()
                self.beat = time.monotonic()
            self.say("resumed")
        elif what == "save":
            self.say("saved" if self.save_state(".state") else "error Couldn't save")
        elif what == "load":
            ok = self.load_state(".state")
            self.say("nostate" if ok is None else "loaded" if ok else "error That save wouldn't load")
        elif what == "reset":
            self.core.lib.retro_reset()
            self.say("reset")
        elif what == "keep":
            self.keep()
        elif what == "volume":
            try:
                self.sound.volume = max(0, min(100, int(arg)))
            except ValueError:
                pass
        elif what == "sound":                          # the sound, elsewhere (Bluetooth headphones came, or went)
            self.args.sound = "" if arg in ("", "-") else arg
            self.sound.stop()
            self.sound = Sound(self.args.sound, self.sound.rate, self.sound.volume)
            if not self.paused:
                self.sound.start()
        elif what == "picture" and arg in PICTURES:
            self.screen.mode = arg
        elif what == "option" and len(words) >= 3:     # an emulator's setting, while it plays (a DS's screens)
            self.core.options[arg] = " ".join(words[2:])
            self.core.options_changed = True
        elif what == "peek":                           # an AI player's look at the game's memory
            out = []
            for spec in words[2:2 + PEEK_RANGES]:
                try:
                    addr, n = (int(v, 16) for v in spec.split(":"))
                except ValueError:
                    addr, n = 0, 0
                data = self.core.peek(addr, n) if 0 < n <= PEEK_MOST else None
                out.append(data.hex() if data is not None else "-")
            self.say("peek", arg, *out)
        elif what == "mem":
            try:
                ok = len(words) > 1 and self.core.dump(" ".join(words[1:]))
            except OSError:
                ok = False
            self.say("mem", "ok" if ok else "none")
        elif what == "shot":                           # ...and its look at the game's picture
            try:
                ok = len(words) > 1 and self.screen.shot(" ".join(words[1:]))
            except (OSError, ValueError):
                ok = False
            self.say("shot", "ok" if ok else "none")
        elif what == "disc":
            try:
                want = int(arg) - 1
            except ValueError:
                want = -1
            if self.core.swap(want):
                self.insert_at = self.frame + SWAP_FRAMES   # (the tray open a moment, as the game expects)
            i, n = self.core.discs()
            self.say("disc", i + 1, n)
        elif what == "quit":
            self.quit = True

    # -- the frames -----------------------------------------------------------------------
    def run(self):
        self.load_saves()
        if self.first_disc and self.core.discs()[0] != self.first_disc[0]:
            self.core.swap(self.first_disc[0], close=True)   # (an emulator that can't start on it: in it goes)
        resumed = False
        if self.args.resume:
            ok = self.load_state(".state.auto")
            if ok is False and self.core.library in LATE_STATES:
                for _ in range(RESUME_TRIES):          # (an N64's takes it only once it's running)
                    self.core.run()
                    ok = self.load_state(".state.auto")
                    if ok:
                        break
                self.core.audio.clear()                # (those frames' sound: not wanted)
            resumed = bool(ok)
        self.screen.clear()
        self.sound.start()
        self.say("ready", "resumed" if resumed else "new")
        i, n = self.core.discs()
        if n > 1:
            self.say("disc", i + 1, n)
        self.beat = time.monotonic()
        skipped = 0
        while not (self.quit or self.core.quit):
            self.commands(0)
            if self.paused:
                self.commands(0.25)
                continue
            for (port, name), at in list(self.letgo.items()):
                if self.frame >= at:
                    self.core.buttons[port] &= ~(1 << BUTTON_IDS[name])
                    del self.letgo[(port, name)]
            if self.insert_at is not None and self.frame >= self.insert_at:
                self.core.shut_tray()                 # the new disc's in
                self.insert_at = None
            rate = int(round(self.core.av.timing.sample_rate))
            if rate != self.sound.rate:               # (the game changed its sound: aplay again)
                self.sound.stop()
                self.sound = Sound(self.args.sound, rate, self.sound.volume)
                self.sound.start()
            period = 1.0 / (self.core.av.timing.fps or 60.0)
            now = time.monotonic()
            if now - self.beat > 0.25:                # a long stall (the Pi busy): start the beat again
                self.beat = now
            self.core.draw = now - self.beat < period or skipped >= SKIP_MOST   # behind: this one isn't drawn
            t = time.perf_counter()
            self.core.run()
            self.stats[2] += time.perf_counter() - t
            self.frame += 1
            self.stats[0] += 1
            if self.core.draw:
                skipped = 0
            else:
                skipped += 1
                self.stats[1] += 1
            win = self.recent[1]
            win[0] += 1
            win[1] += 0 if self.core.draw else 1
            if win[0] >= SLOW_WINDOW:
                self.recent = [win, [0, 0]]
            if self.core.audio:
                self.sound.write(bytes(self.core.audio))
                self.core.audio.clear()
            self.beat += period * (1.0 + self.sound.drift())
            while not (self.quit or self.paused):     # (buttons pressed meanwhile are read at once)
                left = self.beat - time.monotonic()
                if left <= 0:
                    break
                self.commands(left)
            now = time.monotonic()
            if now >= self.next_keep:
                self.next_keep = now + KEEP_EVERY
                self.keep()
            if now - self.stats[4] >= LOG_EVERY:
                n, sk, core_s, pic_s, since = self.stats
                print(f"game: {n / (now - since):.0f} frames a second, {sk} not drawn, the emulator "
                      f"{core_s / max(n, 1) * 1000:.1f} ms a frame, the picture {pic_s / max(n - sk, 1) * 1000:.1f} ms,"
                      f" sound dropped {self.sound.dropped} times", file=sys.stderr, flush=True)
                self.stats = [0, 0, 0.0, 0.0, now]
        if self.core.quit and not self.quit and self.frame < EARLY_END:
            self.say("failed", "This game didn't start")

    def close(self):
        """Saves kept: the in-game one, and where you are (picked up next time)."""
        if self.closed:
            return
        self.closed = True
        self.sound.stop()
        try:
            if self.insert_at is not None:
                self.core.shut_tray()
                self.insert_at = None
            self.keep()
            self.keep_disc()
            self.save_state(".state.auto")
        finally:
            self.core.close()
            self.screen.close()
            self.say("bye")


def main(argv=None):
    ap = argparse.ArgumentParser(description="A game, for Pie-tato's Games tab.")
    ap.add_argument("--core", required=True)
    ap.add_argument("--game", required=True)
    ap.add_argument("--exts", default=".gb,.gbc,.gba,.nes,.sfc,.smc")
    ap.add_argument("--saves", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--system", default="")
    ap.add_argument("--fb", default="/dev/fb0")
    ap.add_argument("--sound", default="")
    ap.add_argument("--volume", type=int, default=80)
    ap.add_argument("--picture", default="Fit", choices=PICTURES)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--option", action="append", default=[], help="an emulator's setting: key=value")
    args = ap.parse_args(argv)
    chan = os.fdopen(os.dup(1), "w", buffering=1)     # (to media mode)
    os.dup2(2, 1)                                     # what cores print goes with the errors
    held = {"session": None, "stop": False}

    def on_signal(*_):                                # (the service stopping, the Pi going off)
        held["stop"] = True
        if held["session"] is not None:
            held["session"].quit = True
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    try:
        os.setpriority(os.PRIO_PROCESS, 0, -4)        # (a little ahead of the rest)
    except OSError:
        pass
    os.set_blocking(0, False)
    try:
        s = Session(args, chan)
    except Exception as ex:
        why = str(ex) if isinstance(ex, GameError) else "This game didn't start"
        print(f"game: couldn't start {args.game}: {ex!r}", file=sys.stderr, flush=True)
        try:
            chan.write(f"error {why}\n")
        except (OSError, ValueError):
            pass
        return 1
    held["session"] = s
    if held["stop"]:
        s.quit = True
    try:
        s.run()
    except Exception as ex:
        print(f"game: {ex!r}", file=sys.stderr, flush=True)
        s.say("error", "The game stopped")
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
