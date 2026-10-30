"""Chromium, from Web's first page on a Pi 4 or 5 that has it (setup.sh puts it in): the whole web, pages as they are,
on the whole screen. pitato/chromium.py runs it on a console of its own; media mode switches to that console and back
(its own in text mode first: a console in graphics mode can't be switched away from). While it's in front the
controller is its mouse: the stick or the d-pad moves the pointer, A clicks (held: drags), B goes back, X types into
the page and START goes to an address or searches (Pietato's keyboard, on Pietato's screen, then the words typed into
Chromium), L and R (or the right stick) scroll, Y right-clicks, SELECT goes to the next tab, L2 and R2 zoom. HOME: its
menu, on Pietato's screen. A keyboard and a mouse are Chromium's own while it's in front."""
import fcntl
import os
import struct
import time

from ..chromium import Chromium, CHROMIUM_VT, cage_kind, chromium_ready, chromium_scale, stop_leftover
from ..library import MEDIA_VT
from ..screen import aplay_device, hdmi_screens, screen_turn, size_of, sound_place
from ..theme import ACCENT, BG, BODY, LINE, MUTED, ROW, TEXT

KD_TEXT, KD_GRAPHICS = 0, 1
KDSETMODE, KDGETMODE = 0x4B3A, 0x4B3B
VT_GETMODE, VT_GETSTATE, VT_ACTIVATE = 0x5601, 0x5603, 0x5606
VT_AUTO = 0
CLEAR = b"\x1b[2J\x1b[H\x1b[?25l"   # a console's words gone, its cursor off
CHROME_SWITCH = 2.0      # seconds a switch of console may take (Chromium's session lets go of the screen first)
CHROME_EARLY = 8.0       # gone this soon after it started: it didn't start
DPAD = ("up", "down", "left", "right")
CHROME_MENU = [("back", "Back to Chromium"), ("address", "Go to an address, or search"),
               ("newtab", "New tab"), ("zoomin", "Zoom in"), ("zoomout", "Zoom out"), ("reload", "Reload the page"),
               ("closetab", "Close this tab"), ("full", "Full screen, or not"), ("away", "Pietato's menus"),
               ("quit", "Close Chromium")]
CHROME_NOTE = {"away": "it stays open"}   # (on the right of its row)
CHROME_KEYS = {"zoomin": ("LEFTCTRL", "EQUAL"), "zoomout": ("LEFTCTRL", "MINUS"), "reload": ("F5",),
               "closetab": ("LEFTCTRL", "W"), "full": ("F11",)}
CHROME_PRESS = {"b": ("LEFTALT", "LEFT"), "select": ("LEFTCTRL", "TAB"), "l2": ("LEFTCTRL", "MINUS"),
                "r2": ("LEFTCTRL", "EQUAL")}   # (back, the next tab, zoom out and in)
CHROME_HELP = [("PAD", "The pointer"), ("A", "Click (hold: drag)"), ("B", "Back"), ("X", "Type, then Enter"),
               ("START", "Address or search"), ("L R", "Scroll"), ("Y", "Right-click"), ("SELECT", "Next tab"),
               ("HOME", "Its menu")]
CHROME_START = [("PAD", "Pointer"), ("A", "Click"), ("B", "Back"), ("HOME", "Its menu")]   # (as it starts)
CHROME_NOTES = [("", "Sticks: the left one is"), ("", "the pointer, the right"), ("", "one scrolls; L2 R2 zoom"),
                ("", ""), ("", "Its menu: zoom, tabs,"), ("", "full screen, close it"), ("", ""),
                ("", "A keyboard and a mouse"), ("", "work in it too")]


class ChromiumScreen:
    """Chromium: opened from Web's first page, worked with the controller while it's in front, its menu on HOME."""

    def chromium_here(self):
        """Chromium's on this Pi (a Pi 4 or 5: setup.sh puts it in), with what it runs in."""
        return chromium_ready()

    def chromium_up(self):
        return getattr(self, "chromium", None) is not None

    def chromium_shown(self):
        """It's in front: the screen's its, and the buttons."""
        return self.chromium_up() and self.view == "chromium"

    def chromium_sticks(self):
        """The sticks are its pointer and its wheel, as they're pushed."""
        return self.active and self.chromium_shown()

    def chromium_leftover(self):
        """At start-up: one the last Pietato left running, stopped."""
        stop_leftover()

    # -- opening it, and closing it ------------------------------------------------------------------------------
    def chromium_open(self, url=None):
        """Chromium in front: started (at url, or its own first page) if it isn't up. The first time, its buttons on
        Pietato's screen first."""
        if self.chromium_up():
            self.chromium_show()
            if url:
                self.chromium.send(("LEFTCTRL", "T"), url, enter=True)   # (in a tab of its own)
            return
        if not self.chromium_here():
            self.toast("Chromium needs a Pi 4 or 5, with it put in by setup.sh", 4)
            return
        st = self.state.setdefault("www", {})
        if not st.get("chromium_seen"):                # (the first time: how it works, then A opens it)
            st["chromium_seen"] = True
            self.save_state()
            self.chrome_url = url
            self.view = "chromehow"
            self.dirty = True
            return
        self.chromium_start(url)

    def chromium_start(self, url=None):
        self.stop()                                    # (its sound needs the speakers: music comes back after it)
        fb = self.fb
        w, h = (fb.real_w, fb.real_h) if fb is not None else (1920, 1080)
        size = f"{fb.dev_w}x{fb.dev_h}" if fb is not None else ""
        shown = (w, h)
        if cage_kind() != "randr":                     # (an older cage: the screen's own size, whatever media mode's)
            own = hdmi_screens()
            shown = size_of(own[0][1][0]) if own else shown
        c = Chromium(w, h)
        self.chromium_front()                          # (its console in front first: its session starts in front)
        if self.fb is not None and self.ttyfd is not None:
            if hasattr(self.fb, "invalidate"):         # (what's there: its console's graphics mode leaves it be, till
                self.fb.invalidate()                   # cage takes the screen)
            self.render_curtain("Chromium", "Starting", hints=CHROME_START)
        ok, why = c.start(url, sound=aplay_device(None, sound_place(self.setting("sound"))[0]), size=size,
                          turn=screen_turn(), scale=chromium_scale(*shown))
        if not ok:
            self.chromium_here_again()
            self.view = "list"
            self.toast(why, 4)
            return
        self.chromium = c
        self.view = "chromium"
        print(f"chromium: started{' at ' + url if url else ''}", flush=True)

    def chromium_close(self, wait=False):
        """Chromium closed (media mode's console in front first, so its session lets go of the screen), back to
        Web's first page."""
        c, self.chromium = getattr(self, "chromium", None), None
        if c is None:
            return
        c.let_go()
        self.chrome_menu = None
        kb = getattr(self, "kb", None)
        if self.view == "keys" and kb and kb.get("chrome"):
            kb["done"] = kb["cancel"] = lambda _text: None
            self.close_keyboard(False)
        if self.view in ("chromium", "chromenu", "keys") or (self.view == "help" and self.help_from == "chromenu"):
            self.view = "list"
        self.chromium_here_again()
        c.close(wait=wait)
        print("chromium: closed", flush=True)
        self.www_list_again()

    def chromium_tick(self, now):
        """Every loop: it closed itself (its last tab closed) or never got going, back to Web's first page."""
        c = getattr(self, "chromium", None)
        if c is None or c.running():
            return
        early = now - c.started < CHROME_EARLY
        print(f"chromium: gone by itself{' (' + c.said + ')' if c.said else ''}", flush=True)
        self.chromium_close()
        self.toast("Chromium didn't start (journalctl -u pietato-chromium says why)" if early else "Chromium closed", 4)

    # -- its console, or media mode's, in front ---------------------------------------------------------------------
    def chromium_front(self):
        """Its console in front. Nothing's drawn there till it's up (graphics mode, while it's nobody's), and
        media mode's goes to text mode first, its words gone: a console in graphics mode can't be switched from."""
        if self.ttyfd is None:
            return
        self.chrome_tty(CHROMIUM_VT, clear=True, mode=KD_GRAPHICS, only_free=True)
        self.chrome_tty(MEDIA_VT, clear=True)
        try:
            fcntl.ioctl(self.ttyfd, KDSETMODE, KD_TEXT)
        except OSError:
            pass
        self.chrome_switch(CHROMIUM_VT)

    def chromium_here_again(self):
        """Media mode's console in front again (Chromium's session lets go of the screen), in graphics mode, its
        menus drawn afresh."""
        c = getattr(self, "chromium", None)
        if c is not None:
            c.let_go()
        if self.ttyfd is not None:
            self.chrome_tty(CHROMIUM_VT, mode=KD_TEXT, only_free=True)   # (nobody's: else it can't be switched from)
            self.chrome_switch(MEDIA_VT)
            self.prog_mode(KD_GRAPHICS)
        if self.fb is not None and hasattr(self.fb, "invalidate"):
            self.fb.invalidate()
        self.dirty = True

    def chrome_tty(self, vt, clear=False, mode=None, only_free=False):
        """A console: its words gone (clear), its mode set. only_free: only while no session has it (one that has it
        says when it may be switched from, and keeps its mode)."""
        try:
            fd = os.open(f"/dev/tty{vt}", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError:
            return
        try:
            if clear:
                os.write(fd, CLEAR)
            if mode is not None:
                free = struct.unpack("bbhhh", fcntl.ioctl(fd, VT_GETMODE, bytes(8)))[0] == VT_AUTO
                if free or not only_free:
                    fcntl.ioctl(fd, KDSETMODE, mode)
        except OSError:
            pass
        finally:
            os.close(fd)

    def chrome_switch(self, vt):
        """That console in front, waiting till it is (for CHROME_SWITCH at most: it may be refused)."""
        try:
            if self.prog_vt() == vt:
                return
            fcntl.ioctl(self.ttyfd, VT_ACTIVATE, vt)
            end = time.monotonic() + CHROME_SWITCH
            while time.monotonic() < end:
                time.sleep(0.03)
                if self.prog_vt() == vt:
                    return
            print(f"chromium: console {vt} didn't come to the front", flush=True)
        except OSError as ex:
            print(f"chromium: no switch to console {vt} ({ex})", flush=True)

    def chromium_show(self):
        """Back to Chromium (from its menu, or Pietato's keyboard)."""
        if not self.chromium_up():
            return
        self.chrome_menu = None
        self.view = "chromium"
        self.chromium_front()

    def chromium_home(self):
        """HOME in Chromium: its menu, or (from the menu, its help or a keyboard over it) back to it. False: not in
        Chromium (Pietato's own menus, with it open or not: HOME as ever)."""
        if not (self.active and self.chromium_up()):
            return False
        kb = getattr(self, "kb", None)
        if self.view == "chromium":
            self.chrome_menu_open()
        elif self.view == "keys" and kb and kb.get("chrome"):
            self.close_keyboard(False)                 # (it goes back to Chromium)
        elif self.view == "chromenu" or (self.view == "help" and self.help_from == "chromenu"):
            self.chromium_show()
        else:
            return False
        return True

    # -- the buttons, while it's in front ---------------------------------------------------------------------------
    def press_chromium(self, name, repeat):
        c = self.chromium
        if name in DPAD:
            if not repeat:
                c.hold(name, True)
            c.nudge(name)
        elif name in ("l", "r"):
            if not repeat:
                c.hold(name, True)
            c.notch(name)
        elif repeat:
            return None
        elif name == "a":
            c.click(True)
        elif name == "y":
            c.click(True, "RIGHT")
            c.click(False, "RIGHT")
        elif name == "x":
            self.chrome_keyboard("Type into the page (then Enter)", lambda text: c.send(None, text, enter=True))
        elif name == "start":
            self.chrome_keyboard("Address, or a search", lambda text: c.send(("LEFTCTRL", "L"), text, enter=True)
                                 if text else None)
        elif name in CHROME_PRESS:
            c.key(*CHROME_PRESS[name])
        return None

    def release_chromium(self, name):
        c = self.chromium
        if name in DPAD or name in ("l", "r"):
            c.hold(name, False)
        elif name == "a":
            c.click(False)

    def chromium_stick(self, axis, value):
        if self.chromium_up():
            self.chromium.stick(axis, value)

    def chrome_keyboard(self, title, then):
        """Pietato's keyboard (Chromium out of the way meanwhile), then back to Chromium: then(what you typed)."""
        self.chromium_here_again()
        self.chrome_menu = None
        self.view = "chromium"                         # (where the keyboard goes back to)

        def done(text):
            self.chromium_show()
            then(text)
        kb = self.open_keyboard(title, "", done, empty=True, limit=300, cancel=lambda _text: self.chromium_show())
        kb["chrome"] = True

    # -- its menu (HOME) ----------------------------------------------------------------------------------------------
    def chrome_menu_open(self):
        self.chromium_here_again()
        self.chrome_menu = {"sel": 0, "confirm": (None, 0.0)}
        self.view = "chromenu"
        self.dirty = True

    def press_chrome_menu(self, name, repeat):
        m = self.chrome_menu
        if m is None or not self.chromium_up():
            self.view = "list"
            self.dirty = True
            return None
        n = len(CHROME_MENU)
        if name in ("up", "down"):
            m["sel"] = (m["sel"] + (1 if name == "down" else -1)) % n
            m["confirm"] = (None, 0.0)
        elif repeat:
            return None
        elif name == "b":
            self.chromium_show()
        elif name == "x":
            self.view, self.help_from = "help", "chromenu"
        elif name == "a":
            job = CHROME_MENU[m["sel"]][0]
            waiting, until = m["confirm"]
            c = self.chromium
            if job == "quit" and (waiting != job or time.monotonic() > until):
                m["confirm"] = (job, time.monotonic() + 4)   # (its tabs go with it: A again, to be sure)
            elif job == "quit":
                self.chromium_close()
                self.toast("Chromium closed", 2)
            elif job == "back":
                self.chromium_show()
            elif job == "away":                        # (Pietato's menus, Chromium still open: Web's first page has
                self.chrome_menu = None                # Back to Chromium)
                self.view = "list"
                i = self.tab_index("www")
                if i is not None:
                    self.tab = i
                    self.www_list_again(keep="www:chromium")
            elif job == "address":
                self.chrome_keyboard("Address, or a search", lambda text: c.send(("LEFTCTRL", "L"), text, enter=True)
                                     if text else None)
            elif job == "newtab":
                self.chrome_keyboard("New tab: an address, or a search",
                                     lambda text: c.send(("LEFTCTRL", "T"), text, enter=bool(text)))
            elif job in CHROME_KEYS:
                self.chromium_show()
                c.send(CHROME_KEYS[job])
        self.dirty = True
        return None

    def render_chrome_menu(self):
        F = self.fonts
        m = self.chrome_menu or {"sel": 0, "confirm": (None, 0.0)}
        img, d = self.canvas(bg=(0, 0, 0))
        W, H = self.fb.w, self.fb.h
        n, mw = len(CHROME_MENU), 360
        rh = 34 if n <= 9 else 31
        mh = 64 + n * rh + 10
        mx0, my0 = (W - mw) / 2, max(12, (H - self.FOOTER - 50 - mh) / 2)   # (room below for a toast)
        d.rounded_rectangle((mx0 - 2, my0 - 2, mx0 + mw + 2, my0 + mh + 2), radius=14, fill=LINE)
        d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + mh), radius=13, fill=BG)
        d.text((mx0 + 22, my0 + 24), "Chromium", font=F["row_b"], fill=TEXT, anchor="lm")
        d.text((mx0 + 22, my0 + 46), "It's still open, as you left it", font=F["small"], fill=MUTED, anchor="lm")
        waiting, until = m["confirm"]
        for k, (job, label) in enumerate(CHROME_MENU):
            ry = my0 + 64 + k * rh
            sel = k == m["sel"]
            self.tappable((mx0, ry - 2, mx0 + mw, ry + rh - 2), "sel", "dict", "chrome_menu", k)
            if sel:
                d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
                d.rounded_rectangle((mx0 + 8, ry + 10, mx0 + 12, ry + rh - 14), radius=2, fill=ACCENT)
            mid = ry + (rh - 4) / 2
            d.text((mx0 + 24, mid), label, font=F["row_b"] if sel else F["row"], fill=TEXT if sel else BODY,
                   anchor="lm")
            if waiting == job and time.monotonic() <= until:
                d.text((mx0 + mw - 22, mid), "press A again", font=F["small"], fill=ACCENT, anchor="rm")
            elif job in CHROME_NOTE:
                d.text((mx0 + mw - 22, mid), CHROME_NOTE[job], font=F["small"], fill=MUTED, anchor="rm")
        self.footer(d, [("A", "Choose"), ("X", "Buttons"), ("B", "Back to Chromium")])
        self.fb.show(img)

    # -- the first time: its buttons, then A opens it -----------------------------------------------------------
    def press_chrome_how(self, name, repeat):
        if repeat:
            return None
        if name == "a":
            self.chromium_start(getattr(self, "chrome_url", None))
        elif name == "b":
            self.view = "list"
            self.dirty = True
        return None

    def render_chrome_how(self):
        img, d = self.canvas()
        self.title_row(d, "Chromium")
        self.help_columns(d, [("In Chromium", CHROME_HELP), ("", CHROME_NOTES)])
        self.footer(d, [("A", "Open Chromium"), ("B", "Back")])
        self.fb.show(img)
