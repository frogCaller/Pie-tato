"""Home Assistant's settings, on the Pi: its address and long-lived token, saved and checked, for the TV Remote and
Lights. Opened from the Home tab (Settings), from the TV Remote or Lights before it's set up, and from
Settings > Home. (The web page's Settings has them too: easier for pasting a token.)"""
import re
import threading
import time

from ..config import settings_glob
from ..homeassistant import HA_FILE, ha_check, ha_typed_url, save_ha
from ..theme import ACCENT, BODY, DONE, MUTED, ROW, TEXT, WARN

HA_TOKEN_SHORTEST = 20     # characters: anything shorter isn't a long-lived token (they're 180 or so)


class HaSettingsScreen:
    """Home Assistant's settings: its IP address (A: type it), Long-lived token (A: type it, or paste it on the web
    page), Check connection (A), Forget (A twice). B closes them, back to where they were opened; L and R go on to the
    next tab as ever."""

    @staticmethod
    def ha_files():
        return [settings_glob(HA_FILE)]

    def ha_open(self):
        """Its settings, over the page you're on: on the row that wants something first."""
        self.hass.load(self.ha_files())
        ha = self.hass
        self.ha_menu = {"sel": 0 if not ha.url else 1 if not ha.token else 2}
        self.ha_said = None
        self.confirm = (None, 0.0)
        self.dirty = True

    def ha_close(self):
        self.ha_menu = None
        self.confirm = (None, 0.0)
        self.load_tab(self.tab)                        # (the page as the settings are now: the TV found, say)
        self.dirty = True

    def ha_value(self):
        """Settings > Home's row, and the Home tab's: where it is, or that it isn't set up."""
        ha = self.hass
        if ha.url and ha.token:
            return ha.where
        return "Not set up" if not (ha.url or ha.token) else "Token not set" if ha.url else "IP address not set"

    def ha_rows(self):
        """(key, label, what it says, its colour)."""
        ha, said = self.hass, self.ha_said
        if said is None:
            check = ("", MUTED) if ha.url and ha.token else ("Set both first", MUTED)
        elif said[0] == "busy":
            check = (said[1], ACCENT)
        else:
            check = (said[1], DONE if said[0] else WARN)
        rows = [("url", "Home Assistant IP address", ha.where if ha.url else "Not set", BODY if ha.url else MUTED),
                ("token", "Long-lived token", "Saved" if ha.token else "Not set", BODY if ha.token else MUTED),
                ("check", "Check connection") + check]
        if ha.url or ha.token:
            rows.append(("forget", "Forget Home Assistant",
                         "press A again" if self.confirm[0] == "ha:forget" and time.monotonic() < self.confirm[1]
                         else "", ACCENT))
        return rows

    def press_ha_menu(self, name, repeat):
        if name in ("l", "r"):
            self.ha_menu = None
            return "pass"
        m, rows = self.ha_menu, self.ha_rows()
        m["sel"] %= len(rows)
        key = rows[m["sel"]][0]
        if name in ("up", "down"):
            m["sel"] = (m["sel"] + (1 if name == "down" else -1)) % len(rows)
        elif repeat:
            pass
        elif name == "b":
            self.ha_close()
        elif name == "a" and key == "url":
            self.open_keyboard("Home Assistant IP address (like 192.168.1.20)", self.hass.where if self.hass.url
                               else "", self.ha_url_typed, limit=120)
        elif name == "a" and key == "token":
            self.open_keyboard("Its long-lived access token (in Home Assistant: your profile, Security)", "",
                               self.ha_token_typed, limit=400)
        elif name == "a" and key == "check":
            self.ha_check_now()
        elif name == "a" and key == "forget":
            if self.confirm[0] == "ha:forget" and time.monotonic() < self.confirm[1]:
                self.confirm = (None, 0.0)
                if self.ha_save({"url": "", "token": ""}):
                    m["sel"] = 0
                    self.toast("Forgot Home Assistant", 3)
            else:
                self.confirm = ("ha:forget", time.monotonic() + 4)
        self.dirty = True
        return None

    def ha_url_typed(self, text):
        url = ha_typed_url(text)                       # (no port: Home Assistant's own, 8123)
        if not re.fullmatch(r"https?://[^/\s]+(/[^\s]*)?", url):
            self.toast("That isn't an address. Try one like 192.168.1.20", 4)
            return
        if not self.ha_save({"url": url}):
            return
        if self.hass.token:
            self.ha_check_now()
        else:                                          # (on to the token)
            self.ha_menu["sel"] = 1
            self.open_keyboard("Its long-lived access token (in Home Assistant: your profile, Security)", "",
                               self.ha_token_typed, limit=400)

    def ha_token_typed(self, text):
        token = "".join(text.split())
        if len(token) < HA_TOKEN_SHORTEST:
            self.toast("That's too short for a long-lived token", 4)
            return
        if self.ha_save({"token": token}):
            self.ha_menu["sel"] = 2
            self.ha_check_now()

    def ha_save(self, updates):
        """Into homeassistant.txt (yours only), and used from now on. False: it couldn't be."""
        try:
            save_ha(updates)
        except OSError as ex:
            self.toast(f"Couldn't save it ({ex.strerror or ex})", 4)
            return False
        self.hass.load(self.ha_files())
        self.lights.load(self.ha_files())
        self.ha_said = None
        self.dirty = True
        return True

    def ha_check_now(self):
        """Whether Home Assistant answers, and takes the token: said on its Check row (and on the web page's)."""
        ha = self.hass
        if not (ha.url and ha.token):
            self.ha_said = (False, "Set the IP address and the token first")
            return
        self.ha_said = ("busy", "Checking…")
        url, token = ha.url, ha.token

        def job():
            said = ha_check(url, token)
            if (self.hass.url, self.hass.token) == (url, token):   # (not changed again meanwhile)
                self.ha_said = said
                self.dirty = True
        threading.Thread(target=job, daemon=True, name="ha-check").start()

    def render_ha_menu(self):
        """Home Assistant's settings, as Settings' pages look."""
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        rows = self.ha_rows()
        sel = self.ha_menu["sel"] % len(rows)
        d.text((20, self.LIST_TOP + 10), "Home  ›  Settings", font=F["small"], fill=MUTED, anchor="lm")
        top, rh = self.LIST_TOP + 26, 46
        for k, (key, label, value, colour) in enumerate(rows):
            y = top + k * rh
            on = k == sel
            if on:
                d.rounded_rectangle((12, y + 2, W - 12, y + rh - 4), radius=10, fill=ROW)
                d.rectangle((12, y + 10, 15, y + rh - 12), fill=ACCENT)
            mid = y + rh / 2 - 1
            d.text((30, mid), label, font=F["row"], fill=(WARN if key == "forget" else TEXT) if on else BODY,
                   anchor="lm")
            if value:
                width = W - 58 - d.textlength(label, font=F["row"]) - 24
                d.text((W - 28, mid), self.fit(d, value, F["small"] if key in ("check", "forget") else F["row"],
                                               width),
                       font=F["small"] if key in ("check", "forget") else F["row"],
                       fill=colour if not on or key in ("check", "forget") else ACCENT, anchor="rm")
        if not self.hass.token:                        # (a token's long: easier pasted on the web page)
            _, ip, _ = self.coder_addresses()
            if ip:
                note = f"Easier on your phone or computer: {ip.split('//', 1)[1]}, Settings"
                d.text((W / 2, H - self.FOOTER - 22), self.fit(d, note, F["small"], W - 40), font=F["small"],
                       fill=MUTED, anchor="mm")
        key = rows[sel][0]
        hints = [("A", {"url": "Type", "token": "Type", "check": "Check", "forget": "Forget"}[key]), ("B", "Back")]
        self.footer(d, hints)
        self.fb.show(img)
