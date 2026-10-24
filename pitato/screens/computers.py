"""Files > Other computers: another computer's files by its address (pitato/computers.py opens them). Anything
that asks the network goes on a thread of its own, so a slow computer, or one that's gone, never holds the
screen up: what it finds comes back to net_tick."""
import os
import threading
import time

from ..computers import folder_name, Trouble
from ..config import home_dir, web_private
from ..util import item, kind_by_name

NET = "net:"                  # Other computers' own places: "net:" (the list) and "net:<address>" (its folders)
SEEN_FRESH = 3.0              # seconds a folder's look stays new enough not to look again on the way in
SCAN_MOST = 5000              # files shown from one folder


def scan(path):
    """A folder on another computer: [(name, is folder, size)]. (Off the screen's thread: it may be slow.)"""
    out = []
    with os.scandir(path) as found:
        for en in found:
            try:
                is_dir = en.is_dir()
                size = 0 if is_dir else en.stat().st_size
            except OSError:
                continue
            out.append((en.name, is_dir, size))
            if len(out) >= SCAN_MOST:
                break
    return out


class ComputersScreen:
    """Files > Other computers."""

    # -- places --------------------------------------------------------------------------
    def is_net(self, path):
        return path.startswith(NET) or path.startswith(self.computers.root + "/")

    def net_up(self, path):
        """Where B (and "..") goes from a place on another computer."""
        if path == NET:
            return home_dir()
        if path.startswith(NET):
            return NET
        found = self.computers.owner(path)
        if not found:
            return NET                                 # (a computer forgotten while you were on it)
        if os.path.normpath(path) == found[2]:
            c = found[0]
            return NET + c["addr"] if c["how"] == "smb" else NET
        return os.path.dirname(path.rstrip("/")) or "/"

    def net_place(self, path):
        """A place on another computer, as the top of the list says it."""
        if path == NET:
            return "Other computers"
        if path.startswith(NET):
            return "Other computers  ›  " + path[len(NET):]
        found = self.computers.owner(path)
        if not found:
            return path
        c, share, top = found
        rel = os.path.relpath(path, top)
        rel = "" if rel == "." else rel
        if c["how"] == "smb":
            return f"{c['addr']}  ›  {share}" + (f"/{rel}" if rel else "")
        return f"{c['addr']}  ›  /{rel}"

    # -- the lists -------------------------------------------------------------------------
    def net_row(self):
        """Other computers, at the top of your home folder."""
        n = len(self.computers.list)
        return item(NET, "Other computers", "netroot", NET,
                    sub=f"{n} added" if n else "Open one by its address")

    def net_list(self, path):
        """The rows for a place on another computer, from what was last seen there; a fresh look is on its way
        (its rows come when it's back)."""
        up = self.net_up(path)
        rows = [item(up, "..", "up", up)]
        if path == NET:
            for c in self.computers.rows():
                rows.append(dict(item(NET + c["addr"], c["addr"], "netpc", NET + c["addr"],
                                      sub="shared folders" if c["how"] == "smb" else "over SSH"), how=c["how"]))
            rows.append(item(NET + "+", "Add a computer", "netadd", NET + "+", sub="By its address"))
            return rows
        if path.startswith(NET):
            addr = path[len(NET):]
            for share in self.net_shares.get(addr, []):
                rows.append(dict(item(f"{path}/{share}", share, "netshare", f"{path}/{share}"), addr=addr, share=share))
            return rows
        when, seen = self.net_seen.get(path, (0.0, None))
        if seen is not None:
            rows += self.net_entries(path, seen)
        if time.monotonic() - when > SEEN_FRESH and (self.net_busy is None or self.net_busy["path"] != path):
            self.net_job("list", path, label="" if seen is not None else "Loading…")
        return rows

    def net_entries(self, path, seen):
        guard = self.web_guard
        dirs, files = [], []
        for name, is_dir, size in seen:
            if name.startswith(".") and (guard or not self.show_hidden):
                continue
            if guard and web_private(name):
                continue
            full = os.path.join(path, name)
            if is_dir:
                dirs.append(item(full, name, "dir", full))
            else:
                files.append(dict(item(full, name, kind_by_name(full), full), size=size))
        dirs.sort(key=lambda x: x["title"].lower())
        files.sort(key=lambda x: x["title"].lower())
        return dirs + files

    def net_refresh(self, path):
        """The list on screen again, if it's this place: the row picked stays picked (or, when the list was still
        coming, the folder you came up from, or the row you were on last time)."""
        bi = self.tab_index("browser")
        if self.cwd != path or bi is None:
            return
        items = self.items.get(bi, [])
        sel = self.sels.get(bi, 0)
        coming = len(items) <= 1
        want = self.net_want.pop(path, None)
        if want is None and not coming and 0 <= sel < len(items):
            want = items[sel]["src"]
        rows = self.items[bi] = self.list_dir(path)
        n = len(rows)
        new = next((k for k, it in enumerate(rows) if it["src"] == want), None) if want else None
        if new is None:
            new = (self.dir_sel.get(path, self.first_row(rows)) if coming else sel)
        self.sels[bi] = max(0, min(new, n - 1))
        self.dirty = True

    # -- opening things -----------------------------------------------------------------------
    def net_open(self, it):
        """A on one of Other computers' rows. True if it was one."""
        kind = it["kind"]
        if kind == "netroot":
            self.browse(NET)
        elif kind == "netadd":
            self.open_keyboard("Computer's address (like 192.168.1.20)", "", self.net_typed, row=0, limit=120)
        elif kind == "netpc":
            addr = it["src"][len(NET):]
            c = self.computers.get(addr)
            if c is None:
                self.browse(NET)
            elif c["how"] == "smb":
                self.browse(NET + addr)
                self.net_job("shares", NET + addr, addr, label="Opening…", user=True)
            else:
                self.net_job("start", NET, addr, label="Opening…", user=True)
        elif kind == "netshare":
            self.net_job("share", self.cwd, it["addr"], it["share"], label="Opening…", user=True)
        else:
            return False
        return True

    def net_typed(self, text):
        self.net_job("add", self.cwd, text, None, None, label="Looking…", user=True)

    def net_login(self, addr, user, then, why=""):
        """A user name and password for a computer, typed: then(user, password)."""
        if why:
            self.toast(why, 3)
        self.open_keyboard(f"User name on {addr}", user or "", lambda u: self.open_keyboard(
            f"Password for {u}", "", lambda pw: then(u, pw), strip=False, empty=True, limit=120),
            limit=120)

    def net_forget(self, it):
        """Y on a computer: press it again to forget it."""
        addr = it["src"][len(NET):]
        key = "netforget:" + addr
        if self.confirm[0] == key and time.monotonic() < self.confirm[1]:
            self.confirm = (None, 0.0)
            self.net_job("forget", NET, addr, label="Forgetting…", user=True)
        else:
            self.confirm = (key, time.monotonic() + 4)
            self.toast(f"Press Y again to forget {addr}", 4)
        self.dirty = True

    # -- the network's part, off the screen's thread -------------------------------------------------
    def net_job(self, what, path, *args, label="", user=False):
        """Something to ask the network: its answer comes back to net_tick. path: the place it's for (the list
        shows label there meanwhile); user: someone pressed something for it (it's worth a word if it fails)."""
        self.net_token += 1
        job = {"token": self.net_token, "what": what, "path": path, "args": args, "label": label, "user": user,
               "from": self.cwd}
        if user or self.net_busy is None or self.net_busy.get("user") is not True:
            self.net_busy = job
        threading.Thread(target=self.net_work, args=(job,), daemon=True).start()
        self.dirty = True

    def net_work(self, job):
        what, args, out, trouble = job["what"], job["args"], None, None
        try:
            if what == "shares":
                out = self.computers.shares(args[0])
            elif what == "list":
                self.computers.ensure(job["path"])
                out = scan(job["path"])
            elif what == "share":
                where = self.computers.open(args[0], args[1])
                out = (where, scan(where))
            elif what == "start":
                where = self.computers.start(args[0])
                out = (where, scan(where))
            elif what == "add":
                addr, (how, found) = self.computers.add(*args)
                out = (addr, how, found, scan(found) if how == "path" else None)
            elif what == "signin":
                self.computers.sign_in(*args[:3])
                out = True
            elif what == "forget":
                self.computers.forget(args[0])
                out = True
        except Trouble as t:
            trouble = t
        except Exception as ex:                        # (a folder that went away, say)
            trouble = Trouble("failed", f"Couldn't open that ({getattr(ex, 'strerror', None) or ex})")
        self.net_done.append((job, out, trouble))
        self.dirty = True

    def net_tick(self):
        """What the network work found, put on the screen (on the screen's thread)."""
        if self.net_changed:                           # (the web page added or forgot one)
            self.net_changed = False
            if self.cwd == NET:
                self.net_refresh(NET)
        while self.net_done:
            job, out, trouble = self.net_done.pop(0)
            if self.net_busy is not None and self.net_busy["token"] == job["token"]:
                self.net_busy = None
            self.net_landed(job, out, trouble)
            self.dirty = True

    def net_here(self, job):
        """Still where it was asked from: the Files list, on the same place."""
        bi = self.tab_index("browser")
        return (self.active and self.tab == bi and self.view in ("list", "keys") and self.cwd == job["from"]
                and self.kb is None)

    def net_landed(self, job, out, trouble):
        what, args = job["what"], job["args"]
        if trouble is not None:
            if what == "list":                         # (not again straight away)
                self.net_seen[job["path"]] = (time.monotonic(), self.net_seen.get(job["path"], (0.0, None))[1])
            self.net_trouble(job, trouble)
            return
        if what == "shares":
            self.net_shares[args[0]] = out
            self.net_refresh(job["path"])
        elif what == "list":
            self.net_seen[job["path"]] = (time.monotonic(), out)
            self.net_refresh(job["path"])
        elif what in ("share", "start"):
            where, seen = out
            self.net_seen[where] = (time.monotonic(), seen)
            if self.net_here(job):
                self.browse(where)
        elif what == "add":
            addr, how, found, seen = out
            if how == "shares":
                self.net_shares[addr] = found
                place = NET + addr
            else:
                self.net_seen[found] = (time.monotonic(), seen)
                place = found
            self.toast(f"Added {addr}", 2)
            if self.net_here(job):
                self.browse(place)
        elif what == "signin":
            self.toast("Signed in", 2)
            again = args[3]                            # what it was for: done now
            if again:
                self.net_job(again[0], job["from"], *again[1:], label="Opening…", user=True)
            self.net_refresh(job["from"])
        elif what == "forget":
            self.net_shares.pop(args[0], None)
            self.toast(f"Forgot {args[0]}", 2)
            self.net_refresh(NET)

    def net_trouble(self, job, t):
        what, args = job["what"], job["args"]
        if not job["user"]:                            # a look on the way in: say so only if it's on screen
            if self.cwd == job["path"]:
                self.toast(t.text, 4)
            return
        if t.kind in ("login", "bad_login") and self.net_here(job):
            why = t.text if t.kind == "bad_login" else ""
            if what == "add":
                text = args[0]
                self.net_login(text.strip(), args[1] or "",
                               lambda u, pw, text=text: self.net_job("add", job["from"], text, u, pw,
                                                                     label="Signing in…", user=True), why)
                return
            if what in ("share", "start", "shares"):
                addr = args[0]
                c = self.computers.get(addr)
                if c is not None:
                    again = (what,) + tuple(args)
                    self.net_login(addr, c.get("user", ""),
                                   lambda u, pw, addr=addr, again=again: self.net_job(
                                       "signin", job["from"], addr, u, pw, again, label="Signing in…", user=True),
                                   why)
                    return
            if what == "signin":
                again = args[3]
                self.net_login(args[0], args[1],
                               lambda u, pw, addr=args[0], again=again: self.net_job(
                                   "signin", job["from"], addr, u, pw, again, label="Signing in…", user=True), why)
                return
        self.toast(t.text, 5)

    def net_answers(self, path, wait=2.0):
        """Whether a file's computer answers now (a quick look, off the screen's thread): a file on one that's
        gone quiet isn't opened, so the screen never waits on it."""
        done, ok = threading.Event(), []

        def look():
            try:
                os.stat(path)
                ok.append(True)
            except OSError:
                pass
            done.set()
        threading.Thread(target=look, daemon=True).start()
        return done.wait(wait) and bool(ok)

    # -- the web page's part (on its own thread: the screen goes on meanwhile) -------------------------------
    def web_show_look(self, path):
        """The web page is putting something from another computer on the screen: it's looked at here, on the
        web page's own thread, so the screen's thread never has to (web_show uses what this found)."""
        if not (isinstance(path, str) and self.is_net(path) and self.web_may_see(path)):
            return
        try:
            self.computers.ensure(path)
            is_dir = os.path.isdir(path)
            if not is_dir and not os.path.isfile(path):
                return
            folder = path if is_dir else os.path.dirname(path)
            self.net_seen[folder] = (time.monotonic(), scan(folder))
            self.net_shown[path] = "dir" if is_dir else kind_by_name(path)
        except (Trouble, OSError):
            pass

    def web_computers(self, addr=""):
        """The computers added (no passwords), or one's shared folders."""
        if not addr:
            out = []
            for c in self.computers.rows():
                start = c["key"] + ("/" + c["home"] if c["how"] == "ssh" and c["home"] else "")
                out.append({"addr": c["addr"], "key": c["key"], "how": c["how"], "user": c["user"], "start": start})
            return {"computers": out}
        c = self.computers.get(addr)
        if c is None:
            return {"error": "That computer isn't on the list any more", "kind": "gone"}
        if c["how"] != "smb":
            return {"addr": c["addr"], "key": folder_name(c["addr"]), "how": c["how"], "shares": []}
        try:
            shares = self.computers.shares(c["addr"])
        except Trouble as t:
            return {"error": t.text, "kind": t.kind}
        self.net_shares[c["addr"]] = shares
        return {"addr": c["addr"], "key": folder_name(c["addr"]), "how": "smb", "shares": shares}

    def web_computer(self, cmd):
        """The web page's Computers tab: add one, sign in to one, open a folder on one, or forget one."""
        do = cmd.get("do")

        def text(key, most=200):
            v = cmd.get(key)
            return str(v)[:most] if isinstance(v, (str, int)) and str(v) != "" else None
        try:
            if do == "add":
                addr, (how, found) = self.computers.add(text("address") or "", text("user"), text("password"))
                key = folder_name(addr)
                if how == "shares":
                    self.net_shares[addr] = found
                    return {"ok": True, "addr": addr, "key": key, "start": key, "shares": found}
                return {"ok": True, "addr": addr, "key": key,
                        "start": os.path.relpath(found, self.computers.root)}
            if do == "signin":
                c = self.computers.get(text("addr") or "")
                if c is None:
                    return {"error": "That computer isn't on the list any more", "kind": "gone"}
                self.computers.sign_in(c["addr"], text("user") or "", text("password") or "")
                return {"ok": True}
            if do == "open":
                rel = os.path.normpath(text("path", 4000) or "")
                if rel.startswith("..") or os.path.isabs(rel) or rel == ".":
                    return {"error": "No such folder", "kind": "gone"}
                self.computers.ensure(os.path.join(self.computers.root, rel))
                return {"ok": True}
            if do == "forget":
                self.computers.forget(text("addr") or "")
                return {"ok": True}
        except Trouble as t:
            return {"error": t.text, "kind": t.kind}
        finally:
            if do in ("add", "signin", "forget"):
                self.net_changed = True
                self.dirty = True
        return {"error": "Unknown request"}
