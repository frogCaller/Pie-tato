"""The Radio tab: genres, stations near you, search, and your own."""
import re
import threading
import time

from ..config import read_own_text, settings_file, write_setting
from ..util import item
from ..radio import RADIO_GENRES, RADIO_STATIONS, RADIO_TTL, rb_stations
from ..library import read_streams


class RadioScreen:
    """The Radio tab: genres, stations near you, search, and your own."""

    # -- Radio -----------------------------------------------------------------
    def radio_root(self, tab):
        mine = [dict(it, icon="MINE") for it in read_streams(tab["files"], kind="radio")]
        loc = self.setting("location") or {}
        cc = (loc.get("country") or "").upper()
        rows = mine + [
            dict(item("rsearch:", "Search stations", "radiosearch", "", sub="By name"), icon="FIND"),
            dict(item("rdir:top:" + cc, f"Popular in {cc}" if cc else "Popular worldwide", "radiodir",
                      "top:" + cc, sub="The most played"), icon="TOP"),
        ]
        for name, badge, tags in RADIO_GENRES:
            rows.append(dict(item("rdir:" + name, name, "radiodir", "genre:" + name), icon=badge))
        rp = next(st for st in RADIO_STATIONS if st[0] == "Radio Paradise")
        rows.append(dict(item("url:" + rp[2], rp[0], "radio", rp[2], sub=rp[1]), icon="RP"))
        return rows

    def radio_open(self, key, title):
        """Open a folder of stations: a genre, the most played, or a search."""
        ti = self.tab_index("radio")
        folder = {"key": key, "title": title, "items": []}
        self.radio_stack.append(folder)
        self.items[ti] = folder["items"]
        self.sels[ti] = 0
        self.tops[ti] = 0
        cached = self.state["radio"].get(key)
        if cached and time.time() - cached["t"] < RADIO_TTL and not key.startswith("search:"):
            folder["items"][:] = cached["items"]
        else:
            self.status[ti] = "loading"
            threading.Thread(target=self.radio_fetch, args=(folder,), daemon=True).start()
        self.dirty = True

    def radio_fetch(self, folder):
        ti = self.tab_index("radio")
        key = folder["key"]
        try:
            if key.startswith("genre:"):
                tags = next(t for n, _, t in RADIO_GENRES if n == key[6:])
                found = rb_stations(tags=tags)
            elif key.startswith("top:"):
                found = rb_stations(country=key[4:], limit=50)
            else:
                found = rb_stations(name=key[7:], limit=50)
            folder["items"][:] = found
            if not key.startswith("search:"):
                self.state["radio"][key] = {"t": time.time(), "items": found}
                self.save_state()
            self.status[ti] = None if found else "empty"
        except Exception:
            self.status[ti] = "error"
        self.dirty = True

    def radio_back(self):
        if not self.radio_stack:
            return False
        ti = self.tab_index("radio")
        gone = self.radio_stack.pop()
        self.status[ti] = None
        self.load_tab(ti)
        self.sels[ti] = next((k for k, it in enumerate(self.items[ti]) if it.get("src") == gone["key"]), 0)
        self.dirty = True
        return True

    def radio_save(self, it):
        """Y: a station into radio.txt, so it's in your list for good."""
        try:
            try:
                have = read_own_text(settings_file("radio.txt"))
            except FileNotFoundError:
                have = ""
            src = str(it["src"]).strip()
            if not src or re.search(r"\s", src):
                self.toast("Can't save that one", 2)
                return
            if src in have:
                self.toast("Already in your stations", 2)
                return
            line = f"{' '.join(str(it['title']).replace('|', '/').split()) or src} | {src}\n"
            if not have:
                have = "# Your stations for the Radio tab. One per line:   Name | URL\n"
            elif not have.endswith("\n"):
                have += "\n"
            write_setting("radio.txt", have + line)
            self.toast(f"Saved {it['title']} to your stations", 3)
        except OSError as ex:
            self.toast(f"Couldn't save it ({ex.strerror or ex})", 3)
