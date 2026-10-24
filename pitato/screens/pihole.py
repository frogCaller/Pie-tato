"""The Pi-hole page (in the Home Assistant tab): your Pi-hole's numbers, from Pi-hole itself."""
import threading
import time

from ..library import LIBRARY
from ..pihole import Busy, Denied, NotPihole, TwoFactor, dns_guess, forget_pihole, pihole_url, save_pihole
from ..util import item


class PiholeScreen:
    """The Pi-hole page: Add your Pi-hole (A: its address, then its password, once), then its numbers as its own
    dashboard has them, asked for every few seconds while the page is open; Forget this Pi-hole at the bottom."""

    def pihole_rows(self):
        ph = self.pihole
        if not ph.configured:
            return [item("pihole:add", "Add your Pi-hole", "action", "pihole:add")]
        rows = []
        if ph.error:
            rows.append(dict(item("pihole:error", "Pi-hole", "info", "pihole:error", sub=ph.error), warn=True))
        elif not ph.found:
            rows.append(item("pihole:asking", "Pi-hole", "info", "", sub="asking…"))
        rows += [dict(item("pihole:" + key, label, "info", "", sub=value), warn=worry)
                 for key, label, value, worry in ph.rows]
        return rows + [item("pihole:forget", "Forget this Pi-hole", "action", "pihole:forget")]

    def pihole_files(self):
        return LIBRARY[self.tab_index("pihole")]["files"]

    def pihole_changed(self):
        """Pi-hole answered (on its page's thread): the page again."""
        pi = self.tab_index("pihole")
        if self.tab == pi:
            rows = self.pihole_rows()
            self.items[pi] = rows
            self.sels[pi] = min(self.sels.get(pi, 0), max(len(rows) - 1, 0))
            if self.active and self.view == "list":
                self.dirty = True

    def pihole_close(self):
        self.pihole.stop()

    def press_pihole(self, name, repeat):
        """A: add your Pi-hole, sign in again, ask it again, or forget it (pressed twice). 'pass' leaves the
        rest to the list (up and down, L and R, X, B)."""
        if name != "a":
            return "pass"
        items = self.tab_items()
        sel = self.sels.get(self.tab, 0)
        it = items[sel] if items and sel < len(items) else None
        if repeat or it is None:
            return None
        key, ph = it["key"], self.pihole
        if key == "pihole:add":
            self.open_keyboard("Your Pi-hole's address (like 192.168.1.2)", dns_guess(), self.pihole_typed,
                               row=0, limit=120)
        elif key == "pihole:error" and ph.denied:
            self.pihole_ask_password(ph.url)
        elif key == "pihole:error":
            ph.error, ph.poll_now = None, True        # try again
            ph.start()
            self.items[self.tab] = self.pihole_rows()
        elif key == "pihole:forget":
            if self.confirm[0] == "pihole:forget" and time.monotonic() < self.confirm[1]:
                self.confirm = (None, 0.0)
                self.pihole_forget()
            else:
                self.confirm = ("pihole:forget", time.monotonic() + 4)
        self.dirty = True
        return None

    def pihole_hints(self, it):
        first = None
        if it is not None:
            first = {"pihole:add": "Add", "pihole:forget": "Forget",
                     "pihole:error": "Sign in" if self.pihole.denied else "Try again"}.get(it["key"])
        return ([("A", first)] if first else []) + [("L R", "Tabs"), ("B", "Back")]

    # adding it: its address, then (if it has one) its password, checked on a thread of their own
    def pihole_typed(self, text):
        url = pihole_url(text)
        if not url:
            self.toast("That isn't an address. Try 192.168.1.2", 4)
            return
        self.toast(f"Looking for your Pi-hole at {url.split('://', 1)[1]}…", 10)
        self.pihole_job("probe", url)

    def pihole_ask_password(self, url):
        self.open_keyboard("Your Pi-hole's password (or an app password)", "",
                           lambda pw: self.pihole_job("signin", url, pw), strip=False, limit=120)

    def pihole_job(self, what, url, password=""):
        def work():
            try:
                if what == "probe":
                    version, needs = self.pihole.probe(url)
                    out = ("needs" if needs else "ok", url, "", version, None)
                else:
                    version, sid = self.pihole.check(url, password)
                    out = ("ok", url, password, version, sid)
            except Denied:
                out = ("denied", url, "", None, None)
            except TwoFactor:
                out = ("twofactor", url, "", None, None)
            except Busy:
                out = ("busy", url, "", None, None)
            except NotPihole:
                out = ("notpihole", url, "", None, None)
            except Exception:
                out = ("away", url, "", None, None)
            self.pihole_done = out
            self.dirty = True
        if what == "signin":
            self.toast("Signing in to your Pi-hole…", 10)
        threading.Thread(target=work, daemon=True, name="pihole-add").start()

    def pihole_tick(self):
        """(media mode's own thread) what the Pi-hole said, as it's added: the next step."""
        (what, url, password, version, sid), self.pihole_done = self.pihole_done, None
        where = url.split("://", 1)[1]
        if self.tab != self.tab_index("pihole") or self.view not in ("list", "keys"):
            return                                     # (gone elsewhere meanwhile)
        if what == "ok":
            self.pihole_save(url, password, version, sid)
        elif what == "needs":
            self.msg = None
            self.pihole_ask_password(url)
        elif what == "denied":
            self.toast("Your Pi-hole didn't take that password", 4)
            self.pihole_ask_password(url)
        elif what == "twofactor":
            self.toast("Your Pi-hole wants a two-factor code too: use an app password", 5)
            self.pihole_ask_password(url)
        elif what == "busy":
            self.toast("Your Pi-hole has too many signed in: try again in a while", 5)
        elif what == "notpihole":
            self.toast(f"{where} doesn't answer as a Pi-hole", 4)
        else:
            self.toast(f"Can't reach {where}", 4)
        self.dirty = True

    def pihole_save(self, url, password, version=None, sid=None):
        try:
            save_pihole(url, password)
        except OSError as ex:
            self.toast(f"Couldn't save it ({ex.strerror or ex})", 4)
            return
        ph = self.pihole
        ph.loaded = None                               # (signed in afresh: whatever it had before, gone)
        ph.load(self.pihole_files())
        ph.version, ph.sid = version, sid              # (the session it signed in with, kept)
        ph.poll_now = True
        ph.start()
        pi = self.tab_index("pihole")
        self.items[pi] = self.pihole_rows()
        self.sels[pi] = 0
        self.toast("Signed in to your Pi-hole" if password else "Your Pi-hole's added", 3)

    def pihole_forget(self):
        ph = self.pihole
        url, sid = ph.url, ph.sid
        try:
            forget_pihole()
        except OSError as ex:
            self.toast(f"Couldn't change static/pihole.txt ({ex.strerror or ex})", 4)
            return
        ph.stop()
        if sid:                                        # (its session ended, rather than left to run out)
            threading.Thread(target=ph.sign_out, args=(url, sid), daemon=True).start()
        ph.load(self.pihole_files())
        pi = self.tab_index("pihole")
        self.items[pi] = self.pihole_rows()
        self.sels[pi] = 0
        self.toast(f"Forgot {url.split('://', 1)[1]}", 3)
