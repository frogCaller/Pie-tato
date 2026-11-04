"""Your game saves, following you from Pi to Pi (Settings > Share with other Pietatos): a game started here picks up from
whichever of your other Pietatos played it last, if that was later than here (its in-game save and where you left
off, all of them from that one Pietato); and a game played here says so to the others when it's done, so they take
its saves while they're on. A save replaced by a newer one is kept, the last one only, in Games/Saves/.replaced.

Each Pietato's web page answers the others on your network (webui.py: /api/saves, /api/saves/file, /api/saves/news).
How old a save is, is told in seconds (not as a time of day), so two Pis' clocks needn't agree."""
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

SAVE_EXTS = (".srm", ".rtc", ".state", ".state.cheevos", ".state.auto", ".state.auto.cheevos")   # a game's own,
                                                     # named for it (its in-game save, its clock, its saved states)
SAVE_MOST = 64 << 20         # bytes: a save bigger than this stays where it is
SAVE_SLACK = 2.0             # seconds: younger by less than this isn't newer (a save being written, a slow answer)
ASK_TIMEOUT = 2.0            # a Pietato on your network answers quickly, or not at all
GET_TIMEOUT = 30.0           # ...a save on its way: this long at most
TELL_TIMEOUT = 2.0
REPLACED = ".replaced"       # (in the Saves folder: the save a newer one replaced)
SUM = re.compile(r"[0-9a-f]{40}")


def game_name(name):
    """A game's name for its saves (games.py's save_name), as another Pietato may send it: a plain file name, or None."""
    if not isinstance(name, str) or not 0 < len(name) <= 200 or name.startswith("."):
        return None
    if "/" in name or "\\" in name or "\0" in name or name != name.strip() or name in (".", ".."):
        return None
    return name


def file_sum(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_files(saves, name, now=None):
    """A game's saves here: {ext: {"size", "age": seconds since it was written, "sum": its SHA-1}}."""
    out, now = {}, time.time() if now is None else now
    if game_name(name) is None:
        return out
    for ext in SAVE_EXTS:
        path = os.path.join(saves, name + ext)
        try:
            st = os.stat(path)
            if not os.path.isfile(path) or st.st_size > SAVE_MOST:
                continue
            out[ext] = {"size": st.st_size, "age": max(0.0, now - st.st_mtime), "sum": file_sum(path)}
        except OSError:
            continue
    return out


def clean_files(files):
    """Another Pietato's list of a game's saves, only as much of it as makes sense."""
    out = {}
    if not isinstance(files, dict):
        return out
    for ext, f in files.items():
        if ext not in SAVE_EXTS or not isinstance(f, dict):
            continue
        size, age, sm = f.get("size"), f.get("age"), f.get("sum")
        if (isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= SAVE_MOST
                or isinstance(age, bool) or not isinstance(age, (int, float)) or not 0 <= age < 1e10
                or not isinstance(sm, str) or not SUM.fullmatch(sm)):
            continue
        out[ext] = {"size": size, "age": float(age), "sum": sm}
    return out


def newest(files):
    """The youngest of a game's saves (seconds), or None for none."""
    return min((f["age"] for f in files.values()), default=None)


def ask_json(url, timeout=ASK_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": "Pietato"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(1 << 20))


def fetch_file(url, dest, size, timeout=GET_TIMEOUT):
    """A save, into dest: True once it's all there (no more than size bytes)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Pietato"})
    end = time.monotonic() + timeout
    got = 0
    with urllib.request.urlopen(req, timeout=ASK_TIMEOUT * 3) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            got += len(chunk)
            if got > size or time.monotonic() > end:
                return False
            f.write(chunk)
    return got == size


def ask_all(peers, name, ask=ask_json):
    """What each of your other Pietatos has of a game's saves, asked at once: [((url, host), its answer or None)]."""
    answers = [None] * len(peers)

    def one(i, url):
        try:
            answers[i] = ask(f"{url}/api/saves?game={urllib.parse.quote(name)}")
        except (OSError, ValueError):
            answers[i] = None
    threads = [threading.Thread(target=one, args=(i, url), daemon=True) for i, (url, _) in enumerate(peers)]
    for t in threads:
        t.start()
    end = time.monotonic() + ASK_TIMEOUT + 0.5
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    return list(zip(peers, answers))


def pull(saves, name, peers, ask=ask_json, fetch=fetch_file, owner=None, on_fetch=None, force=False):
    """A game's saves from whichever of your other Pietatos (peers: [(its address, its name)]) has the newest, if
    that's newer than here: all of that one's saves of the game that aren't the same here, or none (a save and where
    you left off go together: where you left off here, if that one hasn't one, is put aside with what they replace).
    The name of the Pietato they came from, or None. A game being played on one: not
    from that one (its save is still changing). force: from that one (the only one asked) even if here's are newer
    (it's just sent you the game, to carry on from where it was there)."""
    name = game_name(name)
    if name is None or not peers:
        return None
    mine = save_files(saves, name)
    here = newest(mine)
    best = None
    for (url, host), got in ask_all(peers, name, ask):
        if not isinstance(got, dict) or got.get("on") is not True or got.get("playing"):
            continue
        files = clean_files(got.get("files"))
        n = newest(files)
        if n is None or (here is not None and n >= here - SAVE_SLACK and not force):
            continue
        if best is None or n < best[0]:
            best = (n, url, host, files)
    if best is None:
        return None
    _, url, host, files = best
    todo = {ext: f for ext, f in files.items() if not (ext in mine and mine[ext]["sum"] == f["sum"])}
    if not todo:
        return None
    if on_fetch:
        on_fetch(host)
    parts = {}
    try:
        for ext, f in todo.items():
            part = os.path.join(saves, f".{name}{ext}.part")
            q = urllib.parse.urlencode({"game": name, "ext": ext})
            if not fetch(f"{url}/api/saves/file?{q}", part, f["size"]) or file_sum(part) != f["sum"]:
                raise OSError(f"{name}{ext} didn't come whole")
            parts[ext] = part
        keep = os.path.join(saves, REPLACED)
        os.makedirs(keep, exist_ok=True)
        if owner:
            os.chown(keep, *owner)
        now = time.time()
        for ext, part in parts.items():
            dest = os.path.join(saves, name + ext)
            if os.path.isfile(dest):
                os.replace(dest, os.path.join(keep, name + ext))   # (what it replaces: kept, the last one)
            os.replace(part, dest)
            age = todo[ext]["age"]
            os.utime(dest, (now - age, now - age))     # (as old as it is there: the next look sees the same)
            if owner:
                os.chown(dest, *owner)
        for ext in (".state.auto", ".state.auto.cheevos"):   # where you left off here, from before the save that came,
            dest = os.path.join(saves, name + ext)          # and that one hasn't one: put aside too (it'd take you
            if ext in mine and ext not in files and os.path.isfile(dest):   # back to before that save)
                os.replace(dest, os.path.join(keep, name + ext))
        return host
    except OSError as ex:
        print(f"saves: {name} from {host}: {ex}", flush=True)
        return None
    finally:
        for part in parts.values():
            try:
                os.remove(part)
            except OSError:
                pass
        for ext in todo:
            try:
                os.remove(os.path.join(saves, f".{name}{ext}.part"))
            except OSError:
                pass


def post_json(url, body, timeout=TELL_TIMEOUT):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Pietato"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(1 << 16))


def tell(name, peers, post=post_json):
    """Your other Pietatos told a game's just been played here: they take its saves (each asks for them)."""
    name = game_name(name)
    if name is None:
        return 0
    told = 0
    for url, _ in peers:
        try:
            post(f"{url}/api/saves/news", {"game": name})
            told += 1
        except (OSError, ValueError):
            pass
    return told
