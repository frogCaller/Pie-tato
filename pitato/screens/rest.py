"""Resting, to save the battery: with Settings > Battery saver on (Auto, as it comes, is on while it runs on its
battery: in a GPi Case, or on a laptop's), after a few minutes with nothing happening the screen goes dark. Nothing's
drawn, the page on it stops asking the network for news (Home, Pi-hole, Finance, the weather, the bot's chatter), the
main loop looks around once a second, and Wi-Fi saves its power too. Music and radio keep playing. Any button wakes
it (that press does nothing else), as does the web page (the screen's picture watched there, or anything done there)
or the bot hearing its wake phrase. Never while there's something to watch: a video, a game, a program, the camera,
the Bot at work, a sim, a slideshow, lofi art with a song playing, the keyboard, or the web page looking at the
screen."""
import threading
import time

from ..power import battery_discharging, wifi_power_save
from ..screen import sound_on_hdmi, sound_route
from ..system import wifi_dev

REST_AFTER = 180.0      # seconds with nothing happening before the screen rests
REST_READING = 600.0    # ...with a photo, a PDF or a text open (you may be reading it)
REST_WATCHED = 30.0     # seconds since the web page last asked for the screen's picture: someone's watching it
REST_TICK = 1.0         # seconds between the main loop's looks around while it rests
BATTERY_LOOK = 10.0     # seconds between looks at whether it's on its battery (Auto)


class RestScreen:
    """Settings > Battery saver, and the screen resting."""

    def saver_on(self):
        """The battery saver's on: Settings > Battery saver is On, or Auto (as it comes) while it runs on its battery."""
        v = self.setting("battery")
        return v == "On" if v in ("On", "Off") else self.on_battery()

    def on_battery(self):
        """It runs on its battery: in a GPi Case (the GPi Case 2 not on its dock's TV: the dock charges it), or a
        battery the kernel knows of says it's discharging (a laptop's). Looked at every few seconds."""
        now = time.monotonic()
        seen = getattr(self, "battery_seen", None)
        if seen is not None and now - seen[0] < BATTERY_LOOK:
            return seen[1]
        case = getattr(self, "case", None)
        on = True if case == "2w" else not getattr(self, "dock_on_tv", None) if case == "2" else battery_discharging()
        self.battery_seen = (now, on)
        return on

    def saver_why(self):
        """Why Battery saver's Auto is on or off now, in words."""
        case = getattr(self, "case", None)
        if case == "2" and getattr(self, "dock_on_tv", None):
            return "Off: in its dock"
        return "On: it's running on its battery" if self.on_battery() else "Off: it isn't running on a battery"

    def saver_value(self):
        """Settings > Battery saver's row: Auto says whether it's on now."""
        v = self.setting("battery")
        if v in ("On", "Off"):
            return v
        return "Auto (on)" if self.on_battery() else "Auto (off)"

    # -- resting ---------------------------------------------------------------
    def stir(self):
        """Something happened (a button, the web page, the bot spoken to): the wait for rest starts again, and a resting
        screen wakes (from another thread: the main loop wakes it, at once)."""
        self.stirred = time.monotonic()
        if self.resting:
            if threading.current_thread() is threading.main_thread():
                self.rest_end()
            else:
                self.rest_wake = True
                self.wake()

    def rest_after(self):
        return REST_READING if self.view in ("photo", "pdf", "text") else REST_AFTER

    def worth_watching(self, now):
        """Something on the screen to watch, or that's being worked: it doesn't rest (and the wait for rest starts again
        when it's done)."""
        return bool(
            self.proc_owns_screen() or self.game is not None or self.prog is not None or self.chromium_shown()
            or self.learn or self.view in ("keys", "update", "learn", "keepres", "wait", "sketch", "game", "gamemenu",
                                            "chromenu", "chromehow")
            or (self.view == "list" and (self.on_camera_page() or self.on_coder_page() or self.on_sim_page()
                                         or self.on_mandel_page()))
            or (self.view == "photo" and self.v.get("slideshow")) or (self.now_art() and not self.paused)
            or getattr(self, "remote_pad", None) is not None
            or self.voice.speaking or now < getattr(self, "web_mic_until", 0.0)
            or now - self.web_watched < REST_WATCHED or now < self.halting)

    def rest_tick(self, now):
        """The main loop: the screen rests after a while with nothing happening (the battery saver on), and wakes when
        it's asked to, or when there's something to watch after all."""
        if self.resting:
            if self.rest_wake or not self.active or self.worth_watching(now) or not self.saver_on():
                self.rest_end()
            return
        if not self.active or self.fb is None:
            return
        if self.worth_watching(now):
            self.stirred = now
            return
        if now - self.stirred >= self.rest_after() and self.saver_on():
            self.rest_start()

    def rest_start(self):
        """The screen dark, nothing drawn, the page on it quiet, Wi-Fi saving its power."""
        self.resting, self.rest_wake = True, False
        self.msg = None                                # (nothing's left waiting to be said)
        try:
            from PIL import Image
            self.fb.show(Image.new("RGB", (self.fb.w, self.fb.h)))   # black first (a screen that can't go dark)
        except Exception as ex:
            print(f"rest: {ex!r}", flush=True)
        hdmi_sound = sound_on_hdmi(sound_route(self.setting("sound")))   # (a TV's own sound: kept on, so just black)
        self.screen_off = not hdmi_sound and bool(getattr(self.fb, "power", None) and self.fb.power(False))
        self.rest_pollers(False)
        dev = wifi_dev()
        was = wifi_power_save(dev)
        self.rest_wifi = dev if was is False else None   # (it's put back as it was, after)
        if self.rest_wifi:
            wifi_power_save(dev, True)
        print("resting: the screen's dark till a button's pressed", flush=True)

    def rest_end(self):
        """Awake: the screen on, as it was, the page on it as it was."""
        if not self.resting:
            return
        self.resting = self.rest_wake = False
        self.stirred = time.monotonic()
        if self.screen_off and self.fb is not None and not self.fb.power(True):
            print("rest: the screen didn't say it's on again", flush=True)
        self.screen_off = False
        if self.rest_wifi:
            wifi_power_save(self.rest_wifi, False)
            self.rest_wifi = None
        self.rest_pollers(True)
        self.dirty = True

    def rest_pollers(self, on):
        """What was asking the network for news (Home's TV and lights, Pi-hole, Finance): stopped while it rests, and
        those that were, started again after."""
        if not on:
            self.rest_was = [k for k, running in (
                ("hass", self.hass.running), ("lights", self.lights.running), ("pihole", self.pihole.running),
                ("finance", self.stocks.running or self.crypto.running)) if running]
            self.hass.stop()
            self.lights.stop()
            self.pihole.stop()
            self.fin_stop()
            return
        was, self.rest_was = getattr(self, "rest_was", []), []
        if not self.active:
            return
        for k in was:
            if k == "finance":
                self.fin_start()
            else:
                getattr(self, k).start()
