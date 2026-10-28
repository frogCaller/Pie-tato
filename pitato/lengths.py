"""How long a song or a video is, for the Music and Videos lists: read from the file's own header where that's quick
(MP3, MP4 and M4A, FLAC, WAV, Ogg and Opus), else asked of ffprobe, or mplayer. Starting either of those takes the
best part of a second on a Pi Zero, so a thousand songs kept it busy for a quarter of an hour; their headers take a
second or two."""
import os
import re
import shutil
import struct
import subprocess

MOST = 48 * 3600          # seconds: anything longer is a header misread
MP3_LOOK = 1 << 17        # bytes looked through for an MP3's first frame (after its ID3 tag, however big that is)
OGG_LOOK = 1 << 17        # bytes at the end of an Ogg file looked through for its last page (a page is 64 KB at most)


def syncsafe(b):
    """An ID3 tag's size: 7 bits a byte."""
    return (b[0] & 0x7F) << 21 | (b[1] & 0x7F) << 14 | (b[2] & 0x7F) << 7 | (b[3] & 0x7F)


def after_id3(f):
    """Where the file starts after the ID3v2 tag at its start, or tags (0 without one)."""
    at = 0
    for _ in range(4):
        f.seek(at)
        head = f.read(10)
        if len(head) < 10 or head[:3] != b"ID3" or any(x >= 0x80 for x in head[6:10]):
            break
        at += 10 + syncsafe(head[6:10]) + (10 if head[5] & 0x10 else 0)
    return at


# ---- MP3 ----------------------------------------------------------------------------------------------------------
MP3_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}   # MPEG-1, 2, 2.5
MP3_KBPS = {
    (True, 1): (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),       # MPEG-1 layer III
    (True, 2): (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384),      # MPEG-1 layer II
    (True, 3): (0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448),   # MPEG-1 layer I
    (False, 1): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),          # MPEG-2 and 2.5, layer III
    (False, 2): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),          # ...layer II
    (False, 3): (0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256),     # ...layer I
}


def mp3_frame(b):
    """An MP3 frame's header, 4 bytes: {"key", "spf" (samples a frame), "rate", "kbps", "bytes", "xing" (where an
    Xing or Info header would be in it)}, or None if it isn't one."""
    if len(b) < 4:
        return None
    h = int.from_bytes(b[:4], "big")
    ver, layer, bri, sri = h >> 19 & 3, h >> 17 & 3, h >> 12 & 15, h >> 10 & 3
    if h >> 21 != 0x7FF or ver == 1 or layer == 0 or bri in (0, 15) or sri == 3:
        return None                                   # (0: "free format", which says nothing of its size)
    mpeg1 = ver == 3
    rate, kbps = MP3_RATES[ver][sri], MP3_KBPS[(mpeg1, layer)][bri]
    pad = h >> 9 & 1
    if layer == 3:                                    # layer I
        spf, size = 384, (12000 * kbps // rate + pad) * 4
    else:
        spf = 1152 if mpeg1 or layer == 2 else 576
        size = (144000 if spf == 1152 else 72000) * kbps // rate + pad
    mono = h >> 6 & 3 == 3
    side = (17 if mono else 32) if mpeg1 else (9 if mono else 17)
    return {"key": (ver, layer, sri), "spf": spf, "rate": rate, "kbps": kbps, "bytes": size,
            "xing": 4 + side + (0 if h >> 16 & 1 else 2)}


def mp3_length(f, size):
    start = after_id3(f)
    f.seek(start)
    buf = f.read(MP3_LOOK)
    whole = start + len(buf) >= size - 128            # (all of it read: a very short one)
    i = -1
    while True:                                       # its first frame: one with more of its kind just after it
        i = buf.find(b"\xff", i + 1)                  # (a picture in a tag has look-alikes)
        if i < 0 or i + 4 > len(buf):
            return None
        fr = mp3_frame(buf[i:i + 4])
        if fr is None:
            continue
        at, n = i, 0
        while n < 4:
            nxt = mp3_frame(buf[at:at + 4])
            if nxt is None or nxt["key"] != fr["key"]:
                break
            n, at = n + 1, at + nxt["bytes"]
        if n == 4 or (whole and at + 4 > len(buf)):
            break
    first = buf[i:i + fr["bytes"]]
    for at in (fr["xing"], fr["xing"] - 2, fr["xing"] + 2):      # a VBR file says how many frames it has
        if first[at:at + 4] in (b"Xing", b"Info"):
            flags = int.from_bytes(first[at + 4:at + 8], "big")
            frames = int.from_bytes(first[at + 8:at + 12], "big") if flags & 1 else 0
            if frames:
                return frames * fr["spf"] / fr["rate"]
            break
    if first[36:40] == b"VBRI":                       # (Fraunhofer's way of saying so)
        frames = int.from_bytes(first[50:54], "big")
        if frames:
            return frames * fr["spf"] / fr["rate"]
    end = size
    f.seek(max(0, size - 128))
    if f.read(3) == b"TAG":                           # (an ID3v1 tag at the end)
        end -= 128
    at = i                                            # neither: the same bits a second throughout, it's hoped, as
    for _ in range(40):                               # the frames after the first say. If not, they're counted
        nxt = mp3_frame(buf[at:at + 4])
        if nxt is None:
            break
        if nxt["key"] != fr["key"] or nxt["kbps"] != fr["kbps"]:
            return mp3_count(f, start + i, end, fr)
        at += nxt["bytes"]
    audio = end - (start + i)
    return audio * 8 / (fr["kbps"] * 1000) if audio > 0 else None


def mp3_count(f, pos, end, fr):
    """A VBR file that doesn't say how many frames it has: they're counted, one by one."""
    frames, base, buf = 0, pos, b""
    while pos + 4 <= end:
        if pos + 4 > base + len(buf):
            f.seek(pos)
            base, buf = pos, f.read(1 << 20)
            if len(buf) < 4:
                break
        off = pos - base
        h = mp3_frame(buf[off:off + 4])
        if h is not None and h["key"] == fr["key"]:
            frames += 1
            pos += h["bytes"]
            continue
        nxt = buf.find(b"\xff", off + 1)              # (something else in the way: on to the next frame)
        pos = base + (nxt if nxt >= 0 else len(buf))
    return frames * fr["spf"] / fr["rate"] if frames else None


# ---- MP4, M4A, MOV ---------------------------------------------------------------------------------------------
def mp4_box(f, start, end, kind, most=4096):
    """(where its insides start, where it ends) of the first box of that kind between start and end, or None."""
    pos = start
    for _ in range(most):
        if pos + 8 > end:
            return None
        f.seek(pos)
        head = f.read(16)
        if len(head) < 8:
            return None
        n, typ = struct.unpack(">I4s", head[:8])
        inside = pos + 8
        if n == 1:                                    # (a 64-bit size)
            if len(head) < 16:
                return None
            n, inside = struct.unpack(">Q", head[8:16])[0], pos + 16
        elif n == 0:                                  # (to the end)
            n = end - pos
        if n < inside - pos or pos + n > end:
            return None                               # (not a box: a broken file, or not an MP4 at all)
        if typ == kind:
            return inside, pos + n
        pos += n
    return None


def mp4_length(f, size):
    moov = mp4_box(f, 0, size, b"moov")
    mvhd = moov and mp4_box(f, moov[0], moov[1], b"mvhd")
    if not mvhd:
        return None
    f.seek(mvhd[0])
    data = f.read(32)
    if data[:1] == b"\x01":
        if len(data) < 32:
            return None
        scale, dur = struct.unpack(">IQ", data[20:32])
    else:
        if len(data) < 20:
            return None
        scale, dur = struct.unpack(">II", data[12:20])
        if dur == 0xFFFFFFFF:
            return None
    return dur / scale if scale and dur else None


# ---- FLAC, WAV ------------------------------------------------------------------------------------------------------
def flac_length(f, size):
    f.seek(after_id3(f))
    data = f.read(42)
    if len(data) < 42 or data[:4] != b"fLaC" or data[4] & 0x7F != 0:   # (STREAMINFO comes first)
        return None
    x = int.from_bytes(data[18:26], "big")            # rate (20 bits), channels, bits a sample, samples (36 bits)
    rate, samples = x >> 44, x & ((1 << 36) - 1)
    return samples / rate if rate and samples else None


def wav_length(f, size):
    f.seek(0)
    head = f.read(12)
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        return None
    pos, per_sec = 12, 0
    for _ in range(64):
        f.seek(pos)
        chunk = f.read(8)
        if len(chunk) < 8:
            return None
        kind, n = chunk[:4], struct.unpack("<I", chunk[4:])[0]
        if kind == b"fmt ":
            fmt = f.read(min(n, 16))
            if len(fmt) < 12:
                return None
            per_sec = struct.unpack("<I", fmt[8:12])[0]      # bytes a second
        elif kind == b"data":
            n = min(n, size - pos - 8)                # (a recording that never finished says it's bigger)
            return n / per_sec if per_sec and n > 0 else None
        pos += 8 + n + (n & 1)
    return None


# ---- Ogg: Vorbis and Opus --------------------------------------------------------------------------------------------
def ogg_length(f, size):
    f.seek(0)
    first = f.read(4096)
    if len(first) < 28 or first[:4] != b"OggS":
        return None
    serial = first[14:18]
    packet = first[27 + first[26]:]
    if packet[:7] == b"\x01vorbis" and len(packet) >= 16:
        rate, skip = struct.unpack("<I", packet[12:16])[0], 0
    elif packet[:8] == b"OpusHead" and len(packet) >= 12:
        rate, skip = 48000, struct.unpack("<H", packet[10:12])[0]
    else:
        return None
    back = min(size, OGG_LOOK)
    f.seek(size - back)
    tail = f.read(back)
    at = len(tail)
    while True:                                       # its last page: how many samples there are, by then
        at = tail.rfind(b"OggS", 0, at)
        if at < 0:
            return None
        if at + 18 <= len(tail) and tail[at + 4] == 0 and tail[at + 14:at + 18] == serial:
            granule = struct.unpack("<q", tail[at + 6:at + 14])[0]
            if granule > 0:
                return (granule - skip) / rate if rate and granule > skip else None


QUICK = {".mp3": mp3_length, ".mp4": mp4_length, ".m4a": mp4_length, ".m4v": mp4_length, ".mov": mp4_length,
         ".flac": flac_length, ".wav": wav_length, ".ogg": ogg_length, ".oga": ogg_length, ".opus": ogg_length}


def quick_length(path):
    """Seconds, from the file's header, or None when it can't be told that way."""
    read = QUICK.get(os.path.splitext(path)[1].lower())
    if read is None:
        return None
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            n = read(f, size)
    except (OSError, ValueError, OverflowError, struct.error, IndexError, KeyError, ZeroDivisionError):
        return None
    return float(n) if n and 0 < n < MOST else None


def probe_length(path):
    """A song's or a video's length in seconds (0.0: it can't be told)."""
    n = quick_length(path)
    if n:
        return n
    if not os.path.isfile(path):
        return 0.0
    if shutil.which("ffprobe"):
        try:
            r = subprocess.run(["nice", "-n", "15", "ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=30,
                               stdin=subprocess.DEVNULL)
            n = float(r.stdout.strip().splitlines()[0])
            if 0 < n < MOST:
                return n
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass
    try:
        r = subprocess.run(["nice", "-n", "15", "mplayer", "-identify", "-frames", "0", "-vo", "null", "-ao", "null",
                            path], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        m = re.search(r"^ID_LENGTH=([\d.]+)", r.stdout, re.M)
        return float(m.group(1)) if m else 0.0
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
