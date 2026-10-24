"""The TV menu's Cartoons, Free Movies, News and Sports."""
import threading
import time

from ..util import item
from ..tv import CHANNEL_REFRESH, channel_row, channel_text, ia_row, live_pick, PLEX_FOLDERS, SHELVES
from ..library import LIBRARY


class ChannelScreen:
    """The TV menu's Cartoons, Free Movies, News and Sports."""

    # -- Cartoons, Free Movies, News, Sports ----------------------------------------
    def live_list(self):
        """Plex's Live TV channels, fetched again every few hours."""
        when, chans = self.plex_live
        if not chans or time.time() - when > CHANNEL_REFRESH:
            chans = self.plex.live_channels()
            self.plex_live = (time.time(), chans)
        return chans

    def live_fresh(self):
        when, chans = self.plex_live
        return chans if chans and time.time() - when < CHANNEL_REFRESH else None

    def load_channels(self, i):
        """The list shows at once; Plex's channels follow when they come."""
        self.items[i] = self.channel_root(i)
        if self.status.get(i) != "loading":
            self.status.pop(i, None)
        if (LIBRARY[i].get("pick") in ("news", "sports") and self.plex.signed_in
                and self.live_fresh() is None and self.live_wait.get(i) not in ("loading", "error")):
            self.live_wait[i] = "loading"           # only now, so its answer can't be overwritten
            threading.Thread(target=self.fetch_inline, args=(i,), daemon=True).start()

    def channel_root(self, i):
        """Search; Plex folders and the old cartoons or films by kind (Cartoons, Free Movies);
        Plex's channels (News, Sports: with Search once you're signed in to Plex)."""
        tab = LIBRARY[i]
        pick = tab.get("pick")
        noun = {"toons": "a cartoon", "movies": "a film"}.get(pick, "a channel")
        rows = []
        if pick in SHELVES or self.plex.signed_in:
            rows.append(dict(item("chsearch:" + tab["name"], "Search", "chsearch", "",
                                  sub=f"Find {noun} by name"), icon="find"))
        for title, badge, what in PLEX_FOLDERS.get(pick, []):
            rows.append(dict(item("chdir:live:" + what, title, "chdir", "live:" + what,
                                  sub="Live channels on Plex"), icon=badge))
        if pick in SHELVES:
            shelves, badges, kind = SHELVES[pick]
            for folder, entries in shelves.items():
                rows.append(dict(item(f"chdir:shelf:{folder}", folder, "chdir", "shelf:" + folder,
                                      sub=f"{len(entries)} {kind}"), icon=badges.get(folder, "FILM")))
        if pick in ("news", "sports"):
            rows += self.inline_live(i, pick)
        return rows

    def inline_live(self, i, what):
        """Plex's news or sports channels, or a row saying why they aren't here."""
        name = f"{what.title()} channels"
        if not self.plex.signed_in:
            return [dict(item("chplex", name, "chplex", "", sub="Sign in to Plex"), icon="PLEX")]
        chans = self.live_fresh()
        if chans is not None:
            return [channel_row(c) for c in chans if live_pick(what, c)]
        if self.live_wait.get(i) == "error":
            return [dict(item("chretry", name, "chretry", "", sub="Plex didn't answer"), icon="PLEX")]
        return [dict(item("chwait", name, "chwait", "", sub="Getting them from Plex…"), icon="PLEX")]

    def fetch_inline(self, i):
        try:
            self.live_list()
            self.live_wait.pop(i, None)
        except Exception:
            self.live_wait[i] = "error"
        if not self.chan_stack.get(i):
            self.items[i] = self.channel_root(i)
        self.dirty = True

    def picked(self, tab, chans):
        """Every Plex channel a tab shows (for its search)."""
        pick = tab.get("pick")
        whats = [w for _, _, w in PLEX_FOLDERS.get(pick, [])] or [pick]
        return [c for c in chans if any(live_pick(w, c) for w in whats)]

    def open_dir(self, i, it):
        """A on a folder: old cartoons or films (built in), or Plex's channels of a kind."""
        src = it["src"]
        if src.startswith("shelf:"):
            folder = src[len("shelf:"):]
            shelves = SHELVES.get(LIBRARY[i].get("pick"), ({}, {}, ""))[0]
            self.chan_open(i, it["title"], [ia_row(folder, *t) for t in shelves.get(folder, [])], src=src)
            return
        what = src.split(":", 1)[1]
        if not self.plex.signed_in:
            self.chan_open(i, it["title"], [], src=src, status="noplex")
            return
        chans = self.live_fresh()
        if chans is not None:
            self.chan_open(i, it["title"], [channel_row(c) for c in chans if live_pick(what, c)], src=src)
            return
        folder = self.chan_open(i, it["title"], [], src=src, status="loading")

        def job():
            try:
                rows = [channel_row(c) for c in self.live_list() if live_pick(what, c)]
                failed = None
            except Exception:
                rows, failed = [], "error"
            folder["items"][:] = rows
            if self.chan_stack.get(i) and self.chan_stack[i][-1] is folder:
                self.status[i] = failed or (None if rows else "empty")
            self.dirty = True
        threading.Thread(target=job, daemon=True).start()

    def chan_open(self, i, title, rows, src=None, status=None):
        folder = {"title": title, "items": rows, "src": src}
        self.chan_stack.setdefault(i, []).append(folder)
        self.items[i], self.sels[i], self.tops[i] = rows, 0, 0
        self.status[i] = status or (None if rows else "empty")
        self.dirty = True
        return folder

    def chan_search(self, text):
        """Every word you typed in the name: the old cartoons or films first, then Plex's channels."""
        i = self.tab
        tab = LIBRARY[i]
        pick = tab.get("pick")
        words = text.lower().split()

        def hit(s):
            return all(w in s.lower() for w in words)
        rows = []
        if pick in SHELVES:
            rows = [ia_row(folder, *t) for folder, entries in SHELVES[pick][0].items() for t in entries
                    if hit(f"{folder} {t[0]} {t[1]}")]
        hits = [c for c in self.picked(tab, self.plex_live[1]) if hit(channel_text(c))]
        hits.sort(key=lambda c: (not c["title"].lower().startswith(words[0]) if words else 0,
                                 c["title"].lower()))
        self.chan_open(i, f"“{text}”", rows + [channel_row(c) for c in hits])

    def channels_note(self):
        """Top right of Cartoons, Free Movies, News and Sports: where the list comes from."""
        stack = self.chan_stack.get(self.tab)
        src = (stack[-1].get("src") or "") if stack else ""
        pick = LIBRARY[self.tab].get("pick")
        n = len(self.tab_items())
        if src.startswith("shelf:"):
            return f"{n} {SHELVES[pick][2]} · archive.org"
        if stack and not src:
            return f"{n} found"
        if stack:
            return "from Plex Live TV"
        if pick in SHELVES:
            total = sum(len(t) for t in SHELVES[pick][0].values())
            return f"{total} old {SHELVES[pick][2]}"
        return "Live channels"

    def chan_back(self, i):
        stack = self.chan_stack.get(i)
        if not stack:
            return False
        gone = stack.pop()
        self.status.pop(i, None)
        self.load_tab(i)
        self.sels[i] = next((k for k, it in enumerate(self.items[i]) if it["title"] == gone["title"]), 0)
        self.dirty = True
        return True
