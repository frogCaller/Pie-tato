"""The Settings tab: WiFi, Bluetooth and the rest (where you are is Weather's: its START)."""
import re
import subprocess
import threading
import time

from ..theme import ACCENT, BODY, DONE, LINE, MUTED, ROW, TEXT, WARN
from ..config import SETTINGS, TURN_DEGREES
from ..system import is_pc, nm, nm_why, run_out, wifi_dev, wifi_saved, wifi_scan
from ..screen import (boot_resolution, bt_output_name, hdmi_screens, resolution_choices, set_boot_video,
                      set_terminal_turn, set_turn, sound_cards, sound_name, sound_place)
from ..home import wallpaper
from ..weather import find_me, geocode, place_text
from ..voice import BOT_VOICES, VOICE_MB, voices_here
from ..listen import mics
from ..bot import FRIEND_CHATTER, FRIEND_PAGES
from ..inputs import HALT_WAIT

RES_KEEP = 20          # Settings > Resolution: seconds to keep a new size, or the Pi goes back (it may show nothing)
RES_START = 40         # ...and before that, how long the Pi may take to start and ask


class SettingsScreen:
    """The Settings tab: WiFi, Bluetooth and the rest (where you are is Weather's: its START)."""

    # -- Settings --------------------------------------------------------------
    def current_ssid(self):
        w = self.wifi
        if time.monotonic() - w["ssid_t"] > 5:
            w["ssid_t"] = time.monotonic()
            link = run_out(["iw", "dev", wifi_dev(), "link"])
            m = re.search(r"SSID: (.+)", link)
            w["ssid"] = m.group(1).strip() if m else ""
        return w["ssid"]

    def settings_rows(self):
        if self.set_page == "bluetooth":
            return self.bt_rows()
        if self.set_page == "wifi":
            w = self.wifi
            rows = [("radio", "WiFi", ["On", "Off"])]
            if w["radio"]:
                rows += [("net", n["ssid"], n) for n in w["nets"]]
                rows.append(("other", "Other network…", "A hidden network, by name"))
            return rows
        if self.set_page == "friend":
            rows = [("f_server", "Computer with Ollama", None), ("f_model", "Model", None),
                    ("f_name", "What it calls you", None),
                    ("f_chatter", "Says something by itself", [t for t, _ in FRIEND_CHATTER]),
                    ("f_voice", "Voice", None), ("f_speak", "Says its replies out loud", ["On", "Off"])]
            found = mics()                             # (a microphone plugged in: in a GPi Case, one that isn't
            usable = [c for c in found if not c["plays"]] if getattr(self, "case", None) else found   # its own sound)
            if usable or self.bot_listens():
                rows += [("f_listen", "Listens for you", ["Off", "On"]), ("f_wake", "Wake phrase", None)]
                if len(found) > 1 or self.bot_mic_set():
                    rows.append(("f_mic", "Microphone", ["Auto"] + [c["name"] for c in found]))
            return rows
        if self.set_page == "f_voices":
            ours = [i for i, _, _ in BOT_VOICES]
            return [("v_none", "None", "")] + [("v_pick", n, i) for i, n, _ in BOT_VOICES] + \
                [("v_pick", v, v) for v in sorted(voices_here()) if v not in ours]
        if self.set_page == "f_models":
            fr = self.friend
            rows = [("f_pick", m, m) for m in fr.models]
            return rows or [("f_wait", fr.models_status or "Asking for its models…", None)]
        if self.set_page == "resolution":
            info = self.res_info()
            return [("res", "Auto", None)] + [("res", s, s) for s in info[1]] if info else \
                [("res_none", "No TV or monitor on HDMI", None)]
        return self.settings_root_rows()

    def settings_root_rows(self):
        """Settings' first page: Sound's outputs are this Pi's, Resolution is there for a TV or monitor, and Rotate
        screen for any screen but the GPi Case's own (unless it's turned already: to turn it back)."""
        rows = []
        for key, label, choices in SETTINGS:
            if key == "sound":
                choices = ["Auto"] + [n for _, n in sound_cards()]
            elif key == "resolution" and not self.res_info():
                continue
            elif key == "turn" and getattr(self, "case", None) and not self.res_info() \
                    and self.setting("turn") in (None, "Off"):
                continue
            rows.append((key, label, choices))
        return rows

    def sound_value(self):
        """Settings > Sound's row: Auto says where the sound goes now (Bluetooth headphones, a USB speaker, HDMI...)."""
        choice = self.setting("sound")
        place = sound_place(choice)
        if place[0] == "bluetooth":
            return f"{choice}: {bt_output_name(place[1]) or 'Bluetooth'}"
        if choice in (None, "", "Auto") and place[0]:
            return f"Auto: {sound_name(place[0])}"
        return choice

    def settings_root_index(self, key):
        """Where a row is on Settings' first page, to go back to."""
        keys = [k for k, _, _ in self.settings_root_rows()]
        return keys.index(key) if key in keys else 0

    def press_settings(self, name, repeat):
        if name in ("l", "r"):
            return "pass"                              # tabs, as everywhere
        if self.set_page == "bluetooth":
            return self.press_bluetooth(name, repeat)
        rows = self.settings_rows()
        self.set_sel %= len(rows)
        key, label, extra = rows[self.set_sel]
        if name in ("up", "down"):
            self.set_sel = (self.set_sel + (1 if name == "down" else -1)) % len(rows)
        elif self.set_page == "wifi":
            return self.press_wifi(name, repeat, key, extra)
        elif self.set_page in FRIEND_PAGES:
            return self.press_friend_settings(name, repeat, key, extra)
        elif self.set_page == "resolution":
            self.press_resolution(name, repeat, key, extra)
        elif name == "b":
            return "pass"
        elif key == "pad_swap" and name in ("left", "right", "a"):
            if not repeat:
                self.pad_swap()
        elif name in ("left", "right") and extra and not repeat:
            cur = self.setting(key)
            i = extra.index(cur) if cur in extra else 0
            value = extra[(i + (1 if name == "right" else -1)) % len(extra)]
            self.set_setting(key, value)
        elif name == "a" and not repeat:
            if key == "wifi":
                self.set_page, self.set_sel = "wifi", 1
                self.wifi_rescan()
            elif key == "bluetooth":
                self.bt_open()
            elif key == "resolution":
                self.res_seen = (0.0, None)            # (the screen's sizes, looked at afresh)
                self.set_page, self.confirm = "resolution", (None, 0.0)
                boot = boot_resolution()               # (the row it's on now: Auto's, or the size's)
                self.set_sel = next((k for k, (_, _, s) in enumerate(self.settings_rows()) if s == boot), 0)
            elif key == "homeassistant":
                self.ha_open()
            elif key == "friend":
                self.set_page, self.set_sel = "friend", 0
                self.friend.load(self.friend_files())
                if self.friend.server and self.friend.models_at != self.friend.server:
                    self.friend.fetch_models()
            elif key == "wallpaper" and self.setting("wallpaper") == "Picture":
                pi = self.tab_index("photos")
                self.load_tab(pi)
                if not self.tab_items(pi):
                    self.toast("No pictures in ~/Pictures yet", 3)
                else:
                    self.picking, self.tab = "wallpaper", pi
                    self.toast("Pick a picture for the background", 3)
            elif key == "pad":
                self.start_learn()
            elif extra:
                cur = self.setting(key)
                i = extra.index(cur) if cur in extra else 0
                self.set_setting(key, extra[(i + 1) % len(extra)])
        elif name == "x" and not repeat and key == "pad" and self.pads:
            self.pads.forget()
            self.toast("Back to each controller's standard buttons", 3)
        self.dirty = True
        return None

    # -- Rotate screen: a screen mounted on its side or upside down ----------------------------------------------
    def turn_screen(self):
        """Settings > Rotate screen, put into effect: the menus (and the terminal) turned now; a game or a video
        as it next starts."""
        turn = TURN_DEGREES.get(self.setting("turn"), 0)
        set_turn(turn)
        set_terminal_turn(turn)
        fb = self.fb
        if fb is not None and hasattr(fb, "turn_to") and getattr(fb, "turn", 0) != turn:
            try:
                fb.turn_to(turn)
            except (OSError, ValueError) as ex:
                print(f"rotate screen: {ex}", flush=True)
            self.forget_drawn()                        # (the menus may be another size now)
        self.dirty = True

    def forget_drawn(self):
        """Pictures kept to draw quicker (the Simulator's and the Coder's backgrounds, buttons and last frames),
        forgotten: they were for the menus' size before."""
        self.sim_base, self.sim_panel, self.sim_card = (None, None, None), (None, None, 0.0), (None, None)
        self.sim_shown, self.sim_head, self.sim_feet = (None, None, 0.0, 0.0), (None, None), {}
        self.sim_still, self.sim_mask = (None, None), None
        self.coder_base, self.coder_shown = (None, None, None), (None, None, 0.0, 0.0)
        self.wall, self.home_base = (None, None), (None, None)

    # -- Resolution: a TV or monitor's picture size ---------------------------------
    # The size is the kernel's (video= in cmdline.txt), so the Pi restarts to change it. Then it asks if
    # you'll keep it, and if nothing says yes (the screen may show nothing at that size), it goes back.
    def res_boot(self):
        """At start-up: just restarted at a new size, it asks on the screen even if the Pi starts in the
        terminal. Its answer waits a while for the Pi to start, then goes back by itself."""
        self.res_seen = (0.0, None)              # (when the sizes were looked at, and what they were)
        self.res_until = 0.0                     # a new size goes back then (monotonic), unless it's kept
        self.res_drawn = None                    # ...the seconds left, as last drawn
        if self.setting("resolution_try"):
            self.boot_media = True
            self.res_until = time.monotonic() + RES_START + RES_KEEP

    def res_info(self):
        """(the HDMI screen's own size, [sizes]), or None without one: looked at every few seconds."""
        now = time.monotonic()
        if not self.res_seen[0] or now - self.res_seen[0] > 5:
            self.res_seen = (now, resolution_choices())
        return self.res_seen[1]

    def res_here(self):
        """The screen's size now: "1920x1080" (its own, as the sizes it takes go: not turned, if it's on its
        side)."""
        fb = self.fb
        if not fb:
            return ""
        w, h = getattr(fb, "real_w", fb.w), getattr(fb, "real_h", fb.h)
        return f"{getattr(fb, 'dev_w', w)}x{getattr(fb, 'dev_h', h)}"

    def res_value(self):
        """Settings > Resolution's row: the size the Pi starts at, or Auto, the screen's own."""
        boot = boot_resolution()
        if boot:
            return boot
        info = self.res_info()
        return f"Auto ({info[0]})" if info else "Auto"

    def press_resolution(self, name, repeat, key, extra):
        if repeat:
            return
        if name == "b":
            self.confirm = (None, 0.0)
            self.set_page, self.set_sel = "root", self.settings_root_index("resolution")
        elif name == "a" and key == "res":
            want = "res:" + (extra or "Auto")
            if extra == boot_resolution():
                self.toast("The Pi uses this one now", 3)
            elif self.confirm[0] == want and time.monotonic() < self.confirm[1]:
                self.confirm = (None, 0.0)
                self.res_apply(extra)
            else:
                self.confirm = (want, time.monotonic() + 4)     # A again: the Pi restarts

    def res_apply(self, size):
        """The Pi starts at this size from now on (None: the screen's own), if you keep it."""
        screens = hdmi_screens()
        ports = [p for p, sizes in screens if not size or size in sizes]   # (a second screen: if it takes it)
        if not ports:
            self.toast("The screen doesn't take that size", 4)
            return
        args = [f"video={p}:{size}@60" for p in ports] if size else []
        own = screens[0][1][0]
        if is_pc():                                    # (a PC's GRUB takes a few seconds to put it in)
            self.render_wait("Changing the resolution", "One moment")
        try:
            was = set_boot_video(ports, args)
        except OSError as ex:
            self.toast(f"Couldn't change it: {ex.strerror or ex}", 5)
            return
        self.set_setting("resolution_try", {"to": size or "Auto", "size": size or own, "was": was,
                                            "ports": ports, "from": self.res_here()})
        to = size or own or "the screen's own size"
        self.res_restart(f"To change the resolution to {to}")

    def res_restart(self, why):
        self.halting = time.monotonic() + HALT_WAIT       # nothing draws over it
        self.halt_note = "The Pi didn't restart"
        self.render_wait("Restarting", why)
        self.save_state()
        subprocess.Popen(["systemctl", "reboot"])

    def res_ask(self):
        """Media mode on the screen, just after a restart at a new size: is it the one asked for? Then
        it asks if you'll keep it. If not, the Pi goes back to the one before, quietly."""
        t = self.setting("resolution_try")
        if not t or not self.fb:
            return
        want, here = t.get("size"), self.res_here()
        if want and here != want:                # the screen didn't take it (it's at its own size)
            self.res_undo(restart=False)
            self.toast(f"The screen didn't change to {want}", 5)
            return
        self.view = "keepres"
        self.res_until = time.monotonic() + RES_KEEP
        self.dirty = True

    def res_tick(self, now):
        if not self.res_until:
            return
        if now >= self.res_until:
            self.res_until = 0.0
            if self.setting("resolution_try"):
                self.res_undo()
        elif self.view == "keepres" and self.active and self.res_drawn != self.res_left(now):
            self.dirty = True                    # (the seconds left)

    def res_left(self, now=None):
        return max(0, int(self.res_until - (now or time.monotonic()) + 0.999))

    def res_keep(self):
        """Kept: on to Settings, where it was changed."""
        t = self.setting("resolution_try") or {}
        self.set_setting("resolution_try", None)
        self.res_until = 0.0
        self.open_app(self.tab_index("settings"))
        self.set_page, self.set_sel = "root", self.settings_root_index("resolution")
        self.toast(f"Resolution: {t.get('size') or t.get('to')}", 3)

    def res_undo(self, restart=True):
        """Back to the size before: from the next start-up, and now if restart."""
        t = self.setting("resolution_try") or {}
        try:
            set_boot_video(t.get("ports") or [p for p, _ in hdmi_screens()], t.get("was") or [])
        except OSError as ex:
            print(f"resolution: couldn't go back ({ex})", flush=True)
            restart = False                      # (it'd only start at the same size again)
        self.set_setting("resolution_try", None)
        self.res_until = 0.0
        if self.view == "keepres":
            self.view = "home"
        if restart:
            back = t.get("from")
            self.res_restart(f"Back to {back}" if back else "Back to the size before")

    def press_keep_res(self, name, repeat):
        if not repeat:
            if name == "a":
                self.res_keep()
            elif name == "b":
                self.res_undo()
        return None

    def render_keep_res(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        t = self.setting("resolution_try") or {}
        self.res_drawn = left = self.res_left()
        d.text((W / 2, H / 2 - 74), "Keep this resolution?", font=F["big"], fill=TEXT, anchor="mm")
        d.text((W / 2, H / 2 - 12), t.get("size") or t.get("to") or "", font=F["price"], fill=ACCENT, anchor="mm")
        back = t.get("from") or "the size before"
        d.text((W / 2, H / 2 + 50), f"Going back to {back} in {left} second{'' if left == 1 else 's'}",
               font=F["small"], fill=MUTED, anchor="mm")
        self.footer(d, [("A", "Keep it"), ("B", "Go back")])
        self.fb.show(img)

    # -- WiFi --------------------------------------------------------------------
    def press_wifi(self, name, repeat, key, extra):
        w = self.wifi
        if name == "b" and not repeat:
            self.set_page, self.set_sel = "root", self.settings_root_index("wifi")
            self.confirm = (None, 0.0)
        elif w["busy"]:
            pass                                       # one thing at a time
        elif key == "radio" and name in ("left", "right", "a") and not repeat:
            on = not w["radio"]
            w["busy"], w["status"] = True, "Turning WiFi on…" if on else "Turning WiFi off…"
            threading.Thread(target=self.wifi_job, args=("radio", on), daemon=True).start()
        elif name == "x" and not repeat:
            self.wifi_rescan()
        elif key == "net" and name == "a" and not repeat:
            net = extra
            if net["active"]:
                self.toast(f"Connected to {net['ssid']}", 2)
            elif net["ssid"] in w["saved"] or not net["secure"]:
                self.wifi_connect(net["ssid"], None)
            else:
                self.open_keyboard(f"Password for {net['ssid']}", "",
                                   lambda pw, ssid=net["ssid"]: self.wifi_connect(ssid, pw), strip=False)
        elif key == "net" and name == "y" and not repeat:
            ssid = extra["ssid"]
            if ssid not in w["saved"]:
                self.toast("That network isn't saved", 2)
            elif self.confirm[0] == "forget:" + ssid and time.monotonic() < self.confirm[1]:
                self.confirm = (None, 0.0)
                w["busy"], w["status"] = True, f"Forgetting {ssid}…"
                threading.Thread(target=self.wifi_job, args=("forget", ssid), daemon=True).start()
            else:
                self.confirm = ("forget:" + ssid, time.monotonic() + 4)
                self.toast("Press Y again to forget it" + (" (you'll be disconnected)" if extra["active"] else ""), 4)
        elif key == "other" and name == "a" and not repeat:
            self.open_keyboard("Network name", "", lambda ssid: self.open_keyboard(
                f"Password for {ssid} (empty if open)", "",
                lambda pw, ssid=ssid: self.wifi_connect(ssid, pw or "", hidden=True), strip=False, empty=True))
        self.dirty = True
        return None

    def wifi_rescan(self):
        w = self.wifi
        if w["busy"]:
            return
        w["busy"], w["status"] = True, "Looking for networks…"
        threading.Thread(target=self.wifi_job, args=("scan",), daemon=True).start()

    def wifi_connect(self, ssid, password, hidden=False):
        w = self.wifi
        w["busy"], w["status"] = True, f"Connecting to {ssid}…"
        threading.Thread(target=self.wifi_job, args=("connect", ssid, password, hidden), daemon=True).start()
        self.dirty = True

    def wifi_job(self, what, *args):
        w = self.wifi
        try:
            if what == "radio":
                ok, _, err = nm(["radio", "wifi", "on" if args[0] else "off"], 15)
                if not ok:
                    raise ValueError(err or "Couldn't switch WiFi")
                w["radio"] = args[0]
                if args[0]:
                    time.sleep(3)                      # give it a moment to find networks
            elif what == "forget":
                profile = w["saved"].get(args[0], args[0])
                ok, _, err = nm(["connection", "delete", "id", profile], 15)
                self.toast(f"Forgot {args[0]}" if ok else nm_why(err), 3)
                w["said"] = (ok, f"Forgot {args[0]}" if ok else nm_why(err), time.monotonic())   # (for the web page)
            elif what == "connect":
                ssid, password, hidden = args
                before = w["saved"] = wifi_saved()
                if ssid in before and password is None:
                    ok, _, err = nm(["connection", "up", "id", before[ssid]], 60)
                else:
                    cmd = ["device", "wifi", "connect", ssid]
                    if password:
                        cmd += ["password", password]
                    if hidden:
                        cmd += ["hidden", "yes"]
                    ok, _, err = nm(cmd, 60)
                    if not ok and ssid not in before:  # a wrong password leaves a broken profile behind
                        nm(["connection", "delete", "id", ssid], 15)
                if ok:
                    w["ssid_t"] = 0.0
                    self.toast(f"Connected to {ssid}", 3)
                else:
                    self.toast(f"{ssid}: {nm_why(err)}", 5)
                w["said"] = (ok, f"Connected to {ssid}" if ok else f"{ssid}: {nm_why(err)}", time.monotonic())
            if what != "radio" or w["radio"]:
                ok, out, _ = nm(["radio", "wifi"], 10)
                w["radio"] = not ok or out.strip() != "disabled"
                w["saved"] = wifi_saved()
                w["nets"] = wifi_scan() if w["radio"] else []
            else:
                w["nets"] = []
            w["status"] = None if (w["nets"] or not w["radio"]) else "No networks found. X looks again"
        except ValueError as ex:
            w["status"] = str(ex)
        except Exception as ex:
            w["status"] = f"Something went wrong ({ex})"[:70]
        finally:
            w["busy"] = False
            w["ssid_t"] = 0.0
            self.dirty = True

    def locate_job(self, text):
        """Where you are (Weather's settings, or A on Weather with no place yet): found from the internet address
        (text None), or the towns called that, to pick from."""
        try:
            if text is None:
                try:
                    loc = self.pie.place()               # PiE-ink's place first: the same as its weather's
                except Exception:
                    loc = None
                loc = loc or find_me()
                if not loc:
                    raise ValueError("Couldn't tell from the internet address")
                self.set_setting("location", loc)
                self.loc_status = None
                self.toast(f"Location: {place_text(loc)}", 3)
                self.weather_changed()
                if self.wx_menu:
                    self.wx_menu, self.wx_sel = "menu", 0     # (back to Weather's settings, the place set)
            else:
                self.loc_results = geocode(text)
                self.loc_status = None if self.loc_results else f"Nothing found for “{text}”"
                self.wx_sel = 2 if self.loc_results else 1
        except Exception as ex:
            self.loc_status = (str(ex) if isinstance(ex, ValueError) else "Can't reach the internet")
        self.dirty = True

    def render_settings(self):
        if self.set_page == "bluetooth":
            return self.render_bluetooth()
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        rows = self.settings_rows()
        sel = self.set_sel % len(rows)
        crumb = {"wifi": "Settings  ›  WiFi",
                 "friend": "Settings  ›  Bot", "f_models": "Bot  ›  Model", "f_voices": "Bot  ›  Voice",
                 "resolution": "Settings  ›  Resolution"}.get(self.set_page, "Settings")
        d.text((20, self.LIST_TOP + 10), crumb, font=F["small"], fill=MUTED, anchor="lm")
        boot = boot_resolution() if self.set_page == "resolution" else None
        if self.set_page == "resolution":
            d.text((W - 20, self.LIST_TOP + 10), "Now: " + self.res_here(), font=F["small"], fill=MUTED,
                   anchor="rm")
        if self.set_page in FRIEND_PAGES:
            listening = self.set_page == "friend" and (rows[sel][0] in ("f_listen", "f_wake", "f_mic")
                                                        or (self.ears.job and not self.voice.job))
            voicey = self.set_page == "f_voices" or (self.set_page == "friend" and self.voice.job)
            if listening:
                note, lit = self.listen_note()
            else:
                note = (self.voice.status() or ("Voices from Piper, made on the Pi" if self.voice.supported()
                                                else "Piper doesn't run on this Pi")) if voicey \
                    else self.friend.models_status
                lit = voicey and self.voice.job
            if note:
                d.text((W - 20, self.LIST_TOP + 10), self.fit(d, note, F["small"], 330), font=F["small"],
                       fill=ACCENT if lit else MUTED, anchor="rm")
        top, rh = self.LIST_TOP + 26, 46
        rows_fit = (H - self.FOOTER - top) // rh
        first = max(0, min(sel - rows_fit + 1, len(rows) - rows_fit))
        if self.set_page == "wifi":
            here = self.current_ssid()
            d.text((W - 20, self.LIST_TOP + 10), self.fit(d, f"Connected to {here}" if here else "Not connected",
                                                          F["small"], 320),
                   font=F["small"], fill=DONE if here else WARN, anchor="rm")
        for r, k in enumerate(range(first, min(first + rows_fit, len(rows)))):
            key, label, extra = rows[k]
            y = top + r * rh
            on = k == sel
            if on:
                d.rounded_rectangle((12, y + 2, W - 12, y + rh - 4), radius=10, fill=ROW)
                d.rectangle((12, y + 10, 15, y + rh - 12), fill=ACCENT)
            mid = y + rh / 2 - 1
            self.tappable((0, y, W, y + rh), "sel", "attr", "set_sel", k)
            if self.set_page == "wifi":
                self.wifi_row(d, key, label, extra, mid, on)
                continue
            if self.set_page == "f_voices":
                d.text((30, mid), label, font=F["row"], fill=TEXT if on else BODY, anchor="lm")
                note = next((x for i, _, x in BOT_VOICES if i == extra), "")
                if note:
                    d.text((30 + d.textlength(label, font=F["row"]) + 12, mid + 1),
                           self.fit(d, note, F["small"], 250), font=F["small"], fill=MUTED, anchor="lm")
                job = self.voice.job
                state = ("Using", ACCENT) if extra == self.bot_voice() and (extra or not self.voice_want) else \
                    (f"{job['pct']}%", ACCENT) if job and job["id"] == extra else \
                    ("On the Pi", MUTED) if extra in voices_here() else \
                    ("", MUTED) if not extra else (f"{VOICE_MB} MB", MUTED)
                d.text((W - 28, mid), state[0], font=F["small"], fill=state[1], anchor="rm")
                continue
            if self.set_page == "resolution":
                d.text((30, mid), label, font=F["row"], fill=(TEXT if on else BODY) if key == "res" else MUTED,
                       anchor="lm")
                info = self.res_info()
                if key == "res" and extra is None and info:     # Auto: what the screen asks for
                    d.text((30 + d.textlength(label, font=F["row"]) + 12, mid + 1), f"the screen's own, {info[0]}",
                           font=F["small"], fill=MUTED, anchor="lm")
                if key == "res" and self.confirm[0] == "res:" + (extra or "Auto") \
                        and time.monotonic() < self.confirm[1]:
                    d.text((W - 28, mid), "press A again to restart", font=F["small"], fill=ACCENT, anchor="rm")
                elif key == "res" and extra == boot:
                    d.text((W - 28, mid), "Using", font=F["small"], fill=ACCENT, anchor="rm")
                continue
            if self.set_page == "f_models":
                fr = self.friend
                d.text((30, mid), self.fit(d, label, F["row"], W - 200), font=F["row"],
                       fill=(TEXT if on else BODY) if key == "f_pick" else MUTED, anchor="lm")
                if key == "f_pick" and extra == fr.model:
                    d.text((W - 28, mid), "Using", font=F["small"], fill=ACCENT, anchor="rm")
                continue
            if self.set_page == "friend":
                d.text((30, mid), label, font=F["row"], fill=TEXT if on else BODY, anchor="lm")
                value = self.friend_value(key)
                x1 = W - 28
                if extra and on:
                    d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
                    x1 -= 22
                shown = self.fit(d, value, F["row"], 250)
                d.text((x1, mid), shown, font=F["row"], fill=ACCENT if on else MUTED, anchor="rm")
                if extra and on:
                    d.text((x1 - d.textlength(shown, font=F["row"]) - 10, mid), "◀", font=F["small"],
                           fill=ACCENT, anchor="rm")
                    self.tap_arrows(y, y + rh, x1 - d.textlength(shown, font=F["row"]) - 10, W - 28)
                continue
            d.text((30, mid), label, font=F["row"], fill=TEXT if on else BODY, anchor="lm")
            value = ((self.current_ssid() or "Not connected") if key == "wifi" else
                     self.bt_value() if key == "bluetooth" else
                     self.pad_summary() if key == "pad" else
                     self.pad_swap_value() if key == "pad_swap" else
                     self.friend_summary() if key == "friend" else
                     self.ha_value() if key == "homeassistant" else
                     self.sound_value() if key == "sound" else
                     self.res_value() if key == "resolution" else self.setting(key))
            x1 = W - 28
            if extra and on:                          # ◀ value ▶
                d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
                x1 -= 22
            vw = d.textlength(value, font=F["row"])
            d.text((x1, mid), self.fit(d, value, F["row"], 260), font=F["row"],
                   fill=ACCENT if on else MUTED, anchor="rm")
            x0 = x1 - min(vw, 260)
            if extra and on:
                d.text((x0 - 10, mid), "◀", font=F["small"], fill=ACCENT, anchor="rm")
                self.tap_arrows(y, y + rh, x0 - 10, W - 28)
                x0 -= 28
            if key == "wallpaper":                     # a little preview
                thumb = self.wall_thumb()
                d.rounded_rectangle((x0 - 70, mid - 15, x0 - 14, mid + 17), radius=5, fill=LINE)
                img.paste(thumb, (int(x0 - 68), int(mid - 13)))
            elif key == "accent":
                d.ellipse((x0 - 34, mid - 9, x0 - 16, mid + 9), fill=ACCENT)
        right = None
        if self.set_page == "wifi":
            if self.wifi["status"]:
                d.text((W / 2, H - self.FOOTER - 22), self.wifi["status"], font=F["small"], fill=ACCENT,
                       anchor="mm")
            k = rows[sel][0]
            hints = ([("◀▶", "On / off")] if k == "radio" else
                     [("A", "Connect")] + ([("Y", "Forget")] if k == "net" and rows[sel][1] in self.wifi["saved"]
                                           else []) if k == "net" else [("A", "Add")])
            hints += [("X", "Scan"), ("B", "Back")]
        elif self.set_page == "friend":
            k = rows[sel][0]
            hints = ([("◀▶", "Change")] if k in ("f_chatter", "f_speak", "f_listen", "f_mic") else
                     [("A", "Choose")] if k in ("f_model", "f_voice") else [("A", "Type")])
            hints += [("X", "Check"), ("B", "Back")]
        elif self.set_page == "f_voices":
            k, _, vid = rows[sel]
            here = vid in voices_here()
            hints = [("A", "No voice" if k == "v_none" else "Use this" if here else "Get it")]
            if k == "v_pick" and here:
                hints.append(("X", "Take it off?" if self.confirm[0] == "voicerm:" + vid else "Take it off"))
            hints.append(("B", "Back"))
        elif self.set_page == "f_models":
            hints = ([("A", "Use this")] if rows[sel][0] == "f_pick" else []) + [("X", "Ask again"), ("B", "Back")]
        elif self.set_page == "resolution":
            hints = ([("A", "Use this")] if rows[sel][0] == "res" else []) + [("B", "Back")]
        else:
            key = rows[sel][0]
            hints = [("◀▶", "Change"), ("L R", "Tabs"), ("B", "Home")]
            if key in ("wifi", "bluetooth", "friend", "resolution", "homeassistant"):
                hints = [("A", {"friend": "Set up", "homeassistant": "Set up", "wifi": "Networks",
                                "bluetooth": "Devices"}.get(key, "Change")),
                         ("L R", "Tabs"), ("B", "Home")]
            elif key == "pad":
                hints = [("A", "Set up buttons"), ("X", "Reset"), ("L R", "Tabs"), ("B", "Home")]
            elif key == "pad_swap" and self.pad_in_hand() is not None:   # (which controller: on the right)
                right = self.fit(d, self.pad_in_hand().dev.name.strip(), F["small"], 220)
            elif key == "wallpaper" and self.setting("wallpaper") == "Picture":
                hints.insert(1, ("A", "Pick picture"))
        self.footer(d, hints, right=right)
        self.fb.show(img)

    def wifi_row(self, d, key, label, extra, mid, on):
        """One row of the WiFi page: the switch, a network, or "Other network…"."""
        F, W = self.fonts, self.fb.w
        w = self.wifi
        d.text((30, mid), self.fit(d, label, F["row"], W - 260), font=F["row"], fill=TEXT if on else BODY,
               anchor="lm")
        if key == "radio":
            value = "On" if w["radio"] else "Off"
            d.text((W - 28, mid), value, font=F["row"], fill=ACCENT if on else MUTED, anchor="rm")
            return
        if key == "other":
            d.text((W - 28, mid), extra, font=F["small"], fill=MUTED, anchor="rm")
            return
        net = extra
        x = W - 28                                     # signal bars, then a lock for a password
        bars = 4 if net["signal"] >= 75 else 3 if net["signal"] >= 50 else 2 if net["signal"] >= 25 else 1
        for b in range(4):
            bx = x - (3 - b) * 7 - 5
            h = 5 + b * 4
            d.rectangle((bx, mid + 8 - h, bx + 4, mid + 8), fill=(TEXT if on else BODY) if b < bars else LINE)
        x -= 38
        if net["secure"]:
            d.rounded_rectangle((x - 12, mid - 1, x, mid + 9), radius=2, fill=MUTED)
            d.arc((x - 10, mid - 9, x - 2, mid + 3), 180, 360, fill=MUTED, width=2)
            x -= 22
        tag = "Connected" if net["active"] else "Saved" if net["ssid"] in w["saved"] else ""
        if tag:
            d.text((x, mid), tag, font=F["small"], fill=DONE if net["active"] else MUTED, anchor="rm")

    def wall_thumb(self):
        from PIL import Image
        key = ("thumb", self.setting("wallpaper"), self.setting("picture"))
        if getattr(self, "_wall_thumb", (None,))[0] != key:
            im = wallpaper(self.setting("wallpaper"), (224, 128), self.setting("picture"))
            self._wall_thumb = (key, im.resize((54, 30), Image.LANCZOS))
        return self._wall_thumb[1]
