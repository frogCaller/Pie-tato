"""Disc games: whether a disc image is a PlayStation or a PSP game, told by what's inside it, and its game code
(SLUS-00594, ULUS-10041...) to find its picture by. Also the files a game's made of (a .cue's tracks, an .m3u's
discs), so the Games list shows each game once."""
import os
import re
import struct
import zlib

SECTOR, RAW = 2048, 2352
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"          # the start of every sector of a raw (2352-byte) disc image
DISC_EXTS = (".cue", ".chd", ".pbp", ".m3u", ".iso", ".bin", ".img", ".cso")
FOLDER_HINTS = {   # a folder's name that says what's in it (when the files alone can't)
    "ps1": ("ps1", "psx", "psone", "ps one", "playstation", "playstation 1", "sony playstation"),
    "psp": ("psp", "playstation portable", "sony psp", "sony playstation portable", "sony - playstation portable"),
    "ps2": ("ps2", "playstation 2", "sony playstation 2", "sony - playstation 2"),   # (not played here)
}
DISC_TAG = re.compile(r"\s*\((?:disc|disk|cd)\s*(\d+)(?:\s*of\s*\d+)?\)", re.I)
SONY_CODE = re.compile(r"[A-Z]{4}-\d{5}$")             # a game's code, as Redump knows it (ULUS-10041)
_seen = {}                                          # a file -> (its size and time, what it is)


# ---- reading sectors ---------------------------------------------------------------------------------------
class Sectors:
    """The 2048-byte sectors of a disc image: plain (.iso), or raw 2352-byte ones (.bin)."""

    def __init__(self, f, kind="plain", data_at=0):
        self.f, self.kind, self.data_at = f, kind, data_at

    @classmethod
    def open(cls, f):
        """Plain or raw, whichever the file is."""
        f.seek(0)
        head = f.read(16)
        if head[:12] == SYNC:
            return cls(f, "raw", 24 if head[15] == 2 else 16)
        return cls(f)

    def read(self, lba):
        if self.kind == "raw":
            self.f.seek(lba * RAW + self.data_at)
        else:
            self.f.seek(lba * SECTOR)
        return self.f.read(SECTOR)


class CsoSectors:
    """The sectors of a squeezed PSP disc (.cso): its blocks deflated one by one, a table of where each is."""

    def __init__(self, f):
        f.seek(0)
        magic, _, self.total, self.block, self.version, self.shift, _ = struct.unpack("<4sIQIBBH", f.read(24))
        if magic != b"CISO" or not self.block or self.block % SECTOR or self.block > 1 << 20:
            raise ValueError("not a .cso")
        self.f = f

    def read(self, lba):
        at = lba * SECTOR
        if at >= self.total:
            return b""
        n = at // self.block
        self.f.seek(24 + 4 * n)
        a, b = struct.unpack("<II", self.f.read(8))
        start, end = (a & 0x7FFFFFFF) << self.shift, (b & 0x7FFFFFFF) << self.shift
        self.f.seek(start)
        raw = self.f.read(max(0, min(end - start, self.block + 4096)))
        if (a >> 31 and self.version < 2) or (self.version >= 2 and end - start >= self.block):
            data = raw[:self.block]                        # (kept as it is)
        elif a >> 31:
            return b""                                     # (a newer .cso's other squeezing: not read here)
        else:
            data = zlib.decompressobj(-15).decompress(raw, self.block)
        off = at - n * self.block
        return data[off:off + SECTOR]


# ---- PlayStation discs: their SYSTEM.CNF ---------------------------------------------------------------
def find_file(sectors, name, most=64):
    """(sector, size) of a file in a disc's top folder (ISO 9660), or None."""
    pvd = sectors.read(16)
    if pvd[1:6] != b"CD001":
        return None
    lba, size = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
    want = name.upper()
    for k in range(min(-(-size // SECTOR), most)):
        d = sectors.read(lba + k)
        i = 0
        while i < len(d) and d[i]:
            ln, nl = d[i], d[i + 32]
            entry = d[i + 33:i + 33 + nl].decode("ascii", "replace").upper().split(";")[0]
            if entry == want:
                return struct.unpack_from("<I", d, i + 2)[0], struct.unpack_from("<I", d, i + 10)[0]
            i += ln
    return None


def sony_code(text, boot):
    """SLUS-00594 from a SYSTEM.CNF's BOOT line ('cdrom:\\SLUS_005.94;1'), or ''."""
    m = re.search(boot + r"\s*=\s*cdrom0?:\\*([A-Za-z]{4})[_-]?(\d{3})\.?(\d{2})", text)
    return f"{m.group(1).upper()}-{m.group(2)}{m.group(3)}" if m else ""


def umd_code(sectors):
    """A PSP disc's game code, from its UMD_DATA.BIN ('ULUS-10041|...'), or ''."""
    hit = find_file(sectors, "UMD_DATA.BIN")
    code = sectors.read(hit[0])[:min(hit[1], 64)].split(b"|")[0].decode("ascii", "replace").strip() if hit else ""
    return code if SONY_CODE.match(code) else ""


def iso_info(sectors):
    """('ps1', its game code) for a PlayStation disc (ISO 9660, its SYSTEM.CNF says), ('psp', its code) for a
    PSP's (it says so, or it has a PSP game's folder), ('ps2', '') for a PlayStation 2's (not played here), or
    (None, '') for anything else (a PC's)."""
    pvd = sectors.read(16)
    if pvd[1:6] != b"CD001":
        return None, ""
    sysid = pvd[8:40].decode("ascii", "replace").strip().upper()
    if "PSP" in sysid:
        return "psp", umd_code(sectors)
    hit = find_file(sectors, "SYSTEM.CNF")
    if hit:
        text = sectors.read(hit[0])[:min(hit[1], SECTOR)].decode("ascii", "replace")
        if re.search(r"BOOT2\s*=", text):
            return "ps2", ""
        if re.search(r"BOOT\s*=", text):
            return "ps1", sony_code(text, "BOOT")
    if find_file(sectors, "PSP_GAME") or find_file(sectors, "UMD_DATA.BIN"):
        return "psp", umd_code(sectors)                  # (one made without the PSP's name on it)
    return ("ps1", "") if sysid.startswith("PLAYSTATION") else (None, "")


# ---- each kind of file ------------------------------------------------------------------------------------------
def real_name(path):
    """A file as it's really named, when it's named in another letter case (a .cue made on Windows says
    GAME.BIN for game.bin): the path itself if it's there, or if there's no such file at all."""
    if os.path.exists(path):
        return path
    folder, name = os.path.split(path)
    try:
        hit = next((n for n in os.listdir(folder or ".") if n.lower() == name.lower()), None)
    except OSError:
        hit = None
    return os.path.join(folder, hit) if hit else path


def cue_files(path):
    """The files a .cue's tracks are in (full paths, as they're really named), first first."""
    out = []
    try:
        with open(path, errors="replace") as f:
            for line in f:
                m = re.match(r'\s*FILE\s+(?:"([^"]+)"|(\S+))\s+\w+\s*$', line, re.I)
                if m:
                    out.append(real_name(os.path.normpath(os.path.join(os.path.dirname(path), m.group(1) or m.group(2)))))
    except OSError:
        pass
    return out


def cue_fixed(path, where):
    """A .cue that names its files in another letter case than they have (one made on Windows: GAME.BIN for
    game.bin): a copy in `where` with their real names, as full paths. The .cue itself if it's fine."""
    try:
        with open(path, errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return path
    folder, changed = os.path.dirname(path), False
    for k, line in enumerate(lines):
        m = re.match(r'(\s*FILE\s+)(?:"([^"]+)"|(\S+))(\s+\w+\s*)$', line, re.I)
        name = m and (m.group(2) or m.group(3))
        if not name or os.path.exists(os.path.join(folder, name)):
            continue
        real = real_name(os.path.normpath(os.path.join(folder, name)))
        if os.path.exists(real):
            lines[k] = f'{m.group(1)}"{real}"{m.group(4)}'
            changed = True
    if not changed:
        return path
    os.makedirs(where, exist_ok=True)
    fixed = os.path.join(where, os.path.basename(path))
    with open(fixed, "w") as f:
        f.write("\n".join(lines) + "\n")
    return fixed


def m3u_files(path):
    """The discs an .m3u lists (full paths)."""
    out = []
    try:
        with open(path, errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(os.path.normpath(os.path.join(os.path.dirname(path), line)))
    except OSError:
        pass
    return out


def chd_kind(f):
    """'cd', 'dvd', 'gd' (a Dreamcast's) or None: what a .chd holds, from its notes about itself."""
    head = f.read(124)
    if head[:8] != b"MComprHD":
        return None
    version = struct.unpack_from(">I", head, 12)[0]
    at = struct.unpack_from(">Q", head, 48 if version >= 5 else 36)[0]
    for _ in range(64):
        if not at:
            break
        f.seek(at)
        meta = f.read(16)
        if len(meta) < 16:
            break
        tag = meta[:4]
        if tag in (b"CHT2", b"CHTR", b"CHCD"):
            return "cd"
        if tag == b"DVD ":
            return "dvd"
        if tag == b"CHGD":
            return "gd"
        at = struct.unpack_from(">Q", meta, 8)[0]
    return None


def pbp_info(f):
    """A .pbp: ('ps1', its code) for a PSP-made PlayStation game, ('psp', its code) for a PSP game, or (None, '')
    for an update to one."""
    head = f.read(40)
    if head[:4] != b"\x00PBP":
        return None, ""
    sfo_at = struct.unpack_from("<I", head, 8)[0]
    f.seek(sfo_at)
    sfo = f.read(4096)
    if sfo[:4] != b"\x00PSF":
        return None, ""
    keys_at, data_at, n = struct.unpack_from("<III", sfo, 8)
    vals = {}
    for k in range(min(n, 64)):
        ko, _, ln, _, do = struct.unpack_from("<HHIII", sfo, 20 + 16 * k)
        key = sfo[keys_at + ko:sfo.index(b"\0", keys_at + ko)].decode("ascii", "replace")
        vals[key] = sfo[data_at + do:data_at + do + ln].split(b"\0")[0].decode("ascii", "replace")
    m = re.match(r"([A-Z]{4})(\d{5})", vals.get("DISC_ID", ""))
    code = f"{m.group(1)}-{m.group(2)}" if m else ""
    category = vals.get("CATEGORY", "ME")
    if category == "PG":                               # (an update to a game, not one)
        return None, ""
    return ("ps1" if category == "ME" else "psp"), code


def sniff(path):
    """('ps1' or 'psp', its game code) for a PlayStation or PSP game, by what's in the file ('ps2' for a
    PlayStation 2's); ('cd', '') for a CD in a .chd (very likely a PlayStation's), ('dvd', '') for a DVD in one
    (a PSP's or a PlayStation 2's: it can't say which) or a .cso that can't be read; ('unknown', '') for a .chd
    that doesn't say what it holds; (None, '') when it isn't one."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".m3u":
        first = next(iter(m3u_files(path)), None)
        return sniff(first) if first and os.path.isfile(first) and first.lower() != path.lower() else (None, "")
    if ext == ".cue":
        first = next(iter(cue_files(path)), None)
        if not first or not os.path.isfile(first):
            return None, ""
        path, ext = first, ".bin"
    with open(path, "rb") as f:
        if ext in (".iso", ".bin", ".img"):
            return iso_info(Sectors.open(f))
        if ext == ".chd":
            kind = chd_kind(f)
            return (kind if kind in ("cd", "dvd") else "unknown" if kind is None else None), ""
        if ext == ".pbp":
            return pbp_info(f)
        if ext == ".cso":                              # a PSP game, squeezed (or a PlayStation 2's)
            if f.read(4) != b"CISO":
                return None, ""
            try:
                kind, code = iso_info(CsoSectors(f))
            except (ValueError, zlib.error, struct.error):
                kind, code = None, ""
            return (kind, code) if kind in ("psp", "ps2") else ("dvd", "")
    return None, ""


def folder_hint(path, top):
    """The console the folders a file's in are named for (Games/ps1/...), or None."""
    rel = os.path.relpath(os.path.dirname(path), top) if top else os.path.dirname(path)
    for part in reversed([p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]):
        low = part.lower().strip()
        for key, names in FOLDER_HINTS.items():
            if low in names:
                return key
    return None


def disc_info(path, top=None):
    """(the console: 'ps1', 'psp' or None; the game's code, or '') for a disc image. A folder named for it decides
    what the file can't (a .chd that doesn't say what it holds; a DVD in one, a PSP's unless it's in a ps2
    folder)."""
    try:
        st = os.stat(path)
    except OSError:
        return None, ""
    key = (st.st_size, st.st_mtime)
    hit = _seen.get(path)
    if hit and hit[0] == key:
        found = hit[1]
    else:
        try:
            found = sniff(path)
        except (OSError, ValueError, struct.error, IndexError):
            found = (None, "")
        _seen[path] = (key, found)
    kind, code = found
    if kind == "cd":                                     # a CD in a .chd: a PlayStation's
        return "ps1", code
    if kind == "unknown":                                # (its folder may say)
        return folder_hint(path, top), code
    if kind == "dvd":                                    # a PSP's (unless its folder says a PlayStation 2's)
        return ("psp" if folder_hint(path, top) in (None, "psp") else None), code
    if kind == "ps2":                                    # (not played here)
        return None, ""
    return kind, code


def disc_number(title):
    """(the title without '(Disc 2)', 2) or (title, None)."""
    m = DISC_TAG.search(title)
    if not m:
        return title, None
    return (title[:m.start()] + title[m.end():]).strip(), int(m.group(1))
