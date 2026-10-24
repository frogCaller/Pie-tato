"""Small helpers used all over: files and folders, kinds of file, text, numbers and fetching things."""
import glob
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request

from .config import home_dir


FILE_KINDS = ("dir", "up", "video", "audio", "image", "doc", "text", "pdf", "other")  # files on this Pi


# ---- media mode: file types ---------------------------------------------------
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpg", ".mpeg"}
AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav", ".wma"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
DOC_EXTS = {".docx", ".odt", ".pptx", ".odp", ".xlsx", ".ods", ".rtf",
            ".doc", ".xls", ".ppt"}
TEXT_EXTS = {".txt", ".md", ".log", ".csv", ".tsv", ".json", ".yaml", ".yml",
             ".ini", ".cfg", ".conf", ".toml", ".xml", ".html", ".htm", ".css",
             ".py", ".sh", ".js", ".ts", ".c", ".h", ".cpp", ".rs", ".go",
             ".java", ".srt", ".service", ".rules", ".env", ".lua"}


UA = {"User-Agent": "pitato/1.0 (Raspberry Pi media player)"}


# ---- helpers -----------------------------------------------------------------
def find_files(patterns, exts):
    files = []
    for pattern in patterns:
        for d in glob.glob(pattern):
            for root, dirs, names in os.walk(d):
                dirs[:] = [x for x in dirs if not x.startswith(".")]
                files += [os.path.join(root, n) for n in names
                          if not n.startswith(".")
                          and os.path.splitext(n)[1].lower() in exts]
    return sorted(files, key=lambda p: os.path.basename(p).lower())


def short_path(path):
    h = home_dir()
    return "~" + path[len(h):] if path == h or path.startswith(h + "/") else path


def title_of(path):
    t = os.path.splitext(os.path.basename(path))[0]
    t = re.sub(r"[._]+", " ", t)
    return re.sub(r"\s+", " ", t).strip() or os.path.basename(path)


def item(key, title, kind, src, sub=""):
    return {"key": key, "title": title, "kind": kind, "src": src, "sub": sub}


def classify(path):
    if os.path.isdir(path):
        return "dir"
    return kind_by_name(path)


def kind_by_name(path):
    """A file's kind by its name alone (it's never asked: on another computer, that's a trip there)."""
    ext = os.path.splitext(path)[1].lower()
    for kind, exts in (("video", VIDEO_EXTS), ("audio", AUDIO_EXTS), ("image", IMAGE_EXTS),
                       ("doc", DOC_EXTS), ("text", TEXT_EXTS)):
        if ext in exts:
            return kind
    return "pdf" if ext == ".pdf" else "other"


def looks_like_text(path):
    try:
        with open(path, "rb") as f:
            data = f.read(4096)
        if b"\0" in data:
            return False
        data.decode("utf-8")
        return True
    except (OSError, UnicodeDecodeError):
        return False


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def clock(sec):
    sec = int(max(sec, 0))
    h, m, s = sec // 3600, sec // 60 % 60, sec % 60
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def probe_length(path):
    try:
        r = subprocess.run(
            ["nice", "-n", "15", "mplayer", "-identify", "-frames", "0",
             "-vo", "null", "-ao", "null", path],
            capture_output=True, text=True, timeout=30)
        m = re.search(r"^ID_LENGTH=([\d.]+)", r.stdout, re.M)
        return float(m.group(1)) if m else 0.0
    except (OSError, subprocess.TimeoutExpired):
        return 0.0


def cache_name(path, ext):
    try:
        st = os.stat(path)
        key = f"{path}:{st.st_mtime}:{st.st_size}"
    except OSError:
        key = path
    return hashlib.md5(key.encode()).hexdigest() + ext


def in_home(path):
    """True for a file inside your home folder: the only place pictures get deleted
    or written next to (this runs as root)."""
    home = os.path.realpath(home_dir())
    return os.path.realpath(path).startswith(home + os.sep)


def pictures_dir():
    home = home_dir()
    folder = os.path.join(home, "Pictures")
    if not os.path.isdir(folder):
        st = os.stat(home)
        os.makedirs(folder, exist_ok=True)
        os.chown(folder, st.st_uid, st.st_gid)
    return folder


def write_new(folder, stem, ext, data):
    """A new file <stem><ext> in folder (stem-2, stem-3... if taken), owned like the
    folder. Written under a hidden name first, so the Photos tab never sees half a file."""
    st = os.stat(folder)
    path, n = os.path.join(folder, stem + ext), 2
    while os.path.exists(path):
        path, n = os.path.join(folder, f"{stem}-{n}{ext}"), n + 1
    tmp = os.path.join(folder, "." + os.path.basename(path) + ".part")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.chown(tmp, st.st_uid, st.st_gid)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def save_picture(data, ext=".jpg"):
    """Keeps a picture from the camera in ~/Pictures as camera-<date>-<time>.jpg."""
    return write_new(pictures_dir(), time.strftime("camera-%Y-%m-%d-%H%M%S"), ext, data)


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
