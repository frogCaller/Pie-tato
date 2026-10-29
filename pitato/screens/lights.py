"""The Lights page (through Home Assistant): your lights switched on and off and dimmed, your smart plugs, your
scenes, and all the lights off at once."""
import math
import time

from ..theme import ACCENT, BG, LINE, MUTED
from ..util import item
from ..homeassistant import HA_HELD, LIGHT_STEP


LAMP = (255, 196, 92)          # a light that's on


def lamp(pct):
    """A light's colour on the page: brighter the brighter it is."""
    k = 0.4 + 0.6 * max(0, min(pct, 100)) / 100
    return tuple(int(a + (b - a) * k) for a, b in zip(LINE, LAMP))


class LightsScreen:
    """The Lights page (through Home Assistant): your lights switched on and off and dimmed, your smart plugs, your
    scenes, and all the lights off at once."""

    def lights_rows(self):
        """All the lights off, the scenes (a folder of them) and each light and plug; or, in the folder, each scene."""
        lt = self.lights
        if self.lights_scenes:
            return [dict(item("scene:" + r["entity"], r["name"], "scene", r["entity"]), light=r) for r in lt.scenes()]
        rows = []
        lights = lt.lights()
        if any(r["kind"] == "light" for r in lights):
            on = sum(1 for r in lights if r["on"] and r["kind"] == "light")
            rows.append(item("lights:off", "All lights off", "lightsoff", "", sub=f"{on} on" if on else "all off"))
        scenes = len(lt.scenes())
        if scenes:
            rows.append(item("lights:scenes", "Scenes", "lightscenes", "", sub=f"{scenes} scene{'s' if scenes != 1 else ''}"))
        return rows + [dict(item("light:" + r["entity"], r["name"], "light", r["entity"]), light=r) for r in lights]

    def lights_changed(self):
        """Home Assistant answered (on the lights' thread): the page again."""
        li = self.tab_index("lights")
        if self.tab == li:
            rows = self.lights_rows()
            self.items[li] = rows
            self.sels[li] = min(self.sels.get(li, 0), max(len(rows) - 1, 0))
            if self.active and self.view == "list":
                self.dirty = True

    def lights_close(self):
        self.lights.stop()
        self.lights_scenes = False

    def press_lights(self, name, repeat):
        """A: on or off, or a scene set; left and right: dimmer. 'pass' leaves the rest to the list (up and down,
        L and R, X, B)."""
        li = self.tab
        items = self.tab_items()
        sel = self.sels.get(li, 0)
        it = items[sel] if items and sel < len(items) else None
        if name == "b" and self.lights_scenes:
            if not repeat:
                self.lights_scenes = False
                self.items[li] = self.lights_rows()
                self.sels[li] = next((k for k, x in enumerate(self.items[li]) if x["kind"] == "lightscenes"), 0)
                self.dirty = True
            return None
        if name not in ("a", "left", "right"):
            return "pass"
        if it is None:
            if name == "a" and not repeat and not self.lights.configured:
                self.ha_open()                         # (its address and token)
                return None
            if name == "a" and not repeat and self.lights.configured and self.lights.error:
                self.lights.error = None               # try again
                self.lights.poll_now = True
                self.lights.start()
                self.lights.wake.set()
                self.dirty = True
            return None
        kind = it["kind"]
        if name == "a":
            if repeat:
                return None
            if kind == "lightscenes":
                self.lights_scenes = True
                self.sels[li] = 0
            elif kind == "lightsoff":
                n = self.lights.all_off()
                self.toast("All lights off" if n else "They're all off already", 2)
            elif kind in ("light", "scene"):
                self.lights.toggle(it["light"])
        elif kind == "light":                          # left, right: dimmer
            now = time.monotonic()
            if repeat and now - self.lights_hit < HA_HELD:
                return None                            # (held: a step at a time, gently)
            self.lights_hit = now
            self.lights.dim(it["light"], LIGHT_STEP if name == "right" else -LIGHT_STEP)
        else:
            return None                                # (no paging here: the arrows are the dimmer)
        self.items[li] = self.lights_rows()
        self.dirty = True
        return None

    def lights_art(self, d, x, mid, it):
        """A bulb (lit as bright as the light is), a plug, or a word for the rows that aren't lights."""
        F = self.fonts
        r = it.get("light")
        cx = x + 20
        if it["kind"] == "lightsoff":
            d.rounded_rectangle((x, mid - 10, x + 40, mid + 10), radius=5, outline=ACCENT, width=1)
            d.text((cx, mid), "OFF", font=F["badge"], fill=ACCENT, anchor="mm")
            return x + 52
        if r is None or r["kind"] == "scene":          # a scene: a sparkle
            d.polygon([(cx + math.sin(k * math.pi / 4) * (11 if k % 2 == 0 else 3.5),
                        mid - math.cos(k * math.pi / 4) * (11 if k % 2 == 0 else 3.5)) for k in range(8)], fill=ACCENT)
            return x + 52
        on = r["on"] and not r["gone"]
        colour = lamp(r["pct"] if r["dims"] else 100)
        if r["kind"] == "plug":
            d.rounded_rectangle((cx - 10, mid - 10, cx + 10, mid + 10), radius=6, fill=colour if on else None,
                                outline=colour if on else MUTED, width=2)
            for dx in (-4, 4):
                d.ellipse((cx + dx - 2, mid - 2, cx + dx + 2, mid + 2), fill=BG if on else MUTED)
        elif on:
            d.ellipse((cx - 13, mid - 13, cx + 13, mid + 13), outline=lamp(0), width=2)
            d.ellipse((cx - 9, mid - 9, cx + 9, mid + 9), fill=colour)
        else:
            d.ellipse((cx - 9, mid - 9, cx + 9, mid + 9), outline=MUTED, width=2)
        return x + 52

    def lights_right(self, it):
        """The words on the right of a row, their colour, and how bright (for the bar under its name)."""
        kind = it["kind"]
        if kind in ("lightsoff", "lightscenes"):
            return it.get("sub", ""), MUTED, None
        r = it["light"]
        if r["kind"] == "scene":
            return "", MUTED, None
        if r["gone"]:
            return "not answering", MUTED, None
        if not r["on"]:
            return "off", MUTED, None
        if r["dims"]:
            return f"{r['pct']}%", ACCENT, max(r["pct"], 1) / 100
        return "on", ACCENT, None

    def lights_hints(self, it):
        if it is None:
            if not self.lights.configured:
                return [("A", "Set up"), ("L R", "Tabs"), ("B", "Back")]
            return [("A", "Try again")] * bool(self.lights.error and self.lights.configured) + [("L R", "Tabs"),
                                                                                                 ("B", "Back")]
        kind, r = it["kind"], it.get("light")
        first = {"lightsoff": "All off", "lightscenes": "Open"}.get(kind)
        if first is None:
            first = "Set" if r["kind"] == "scene" else "Turn off" if r["on"] else "Turn on"
        hints = [("A", first)]
        if kind == "light":
            hints.append(("◀▶", "Dimmer" if r["dims"] else "Off / on"))
        return hints + [("L R", "Tabs"), ("B", "Back")]

    def lights_empty(self):
        lt = self.lights
        if not lt.configured:
            return "Connect Home Assistant", "Press A to put in its address and token"
        if lt.error:
            return "Couldn't get your lights", lt.error
        if not lt.found:
            return "Looking for your lights", "One moment"
        if self.lights_scenes:
            return "No scenes", "Make them in Home Assistant"
        return "No lights found", "Name them on the web page: Settings, Home"
