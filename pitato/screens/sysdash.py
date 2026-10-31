"""System's dashboard: this Pi's numbers, drawn as the Pi-hole page draws its own. SELECT switches between it and
System's list (where Update software, Restart media mode, Reboot and Shut down are), and the one you pick is kept."""
import re
import time

from ..config import WEB_PORT
from ..library import LISTEN_KINDS
from ..system import HISTORY_EVERY, HISTORY_KEEP, HOT_C, is_pc, on_pc, uptime_text
from ..theme import ACCENT, BODY, DONE, LINE, MUTED, ROW, TEXT, WARN
from ..util import human_size
from .pihole import PH_ALLOWED, PH_AXIS, PH_CLIENTS, PH_KINDS

# its colours: the Pi-hole page's, each one thing here (too hot, or the SD card nearly full: WARN instead)
SD_CPU = PH_ALLOWED            # how busy the CPU is
SD_TEMP = PH_KINDS[1]          # how hot it is
SD_MEM = PH_CLIENTS            # memory used; the WiFi's signal
SD_DISK = PH_KINDS[3]          # the SD card
SD_PANELS = [("network", "Network"), ("temp", "Temperature, last 5 minutes"), ("pi", "This Pi"),
             ("busy", "In the background")]
TEMP_FULL = 85.0               # °C: the temperature's meter full (the Pi slows itself down from 80)
SIGNAL_RANGE = (-90, -30)      # dBm: the WiFi's signal from none to as good as it gets


def short_size(n):
    """A size short enough for a tile: 231 MB, 7.6 GB (no tenths from 100 up)."""
    text = human_size(n)
    num, _, unit = text.partition(" ")
    try:
        return f"{float(num):.0f} {unit}" if float(num) >= 100 else text
    except ValueError:
        return text


class SysDashScreen:
    """System's dashboard: its four numbers (the CPU's temperature, how busy it is, memory used, the SD card's room
    left), how busy the CPU's been the last 5 minutes (a column every 10 seconds), and below, ◀▶: the network, the
    temperature the last 5 minutes, this Pi, and what Pietato's busy with. SELECT: System's list instead (and
    back again), kept for next time."""

    def sys_dash(self):
        """Whether System shows its dashboard (else its list)."""
        return self.setting("sys_view") != "List"

    def press_sysdash(self, name, repeat):
        """SELECT switches between the dashboard and the list, either way. On the dashboard ◀▶ go through the panels
        below the chart, A updates when there's a new version (twice, as the list's Update software), and ▲▼ have
        nothing to do; the rest is as in any list (L and R, X, B, START). 'pass' leaves a button to the list."""
        if name == "select":
            if not repeat:
                self.set_setting("sys_view", "List" if self.sys_dash() else "Dashboard")
                self.confirm = (None, 0.0)             # (a button pressed once in the list: not any more)
            return None
        if not self.sys_dash():
            return "pass"
        if name in ("left", "right"):
            if not repeat:
                self.sys_panel = (self.sys_panel + (1 if name == "right" else -1)) % len(SD_PANELS)
                self.dirty = True
            return None
        if name == "a":
            if not repeat and self.updater.available():
                self.system_action({"src": "update"})  # (as the list's Update software: A again to go ahead)
            return None
        if name in ("up", "down"):
            return None
        return "pass"

    def sysdash_hints(self):
        hints = ([("A", "Update")] if self.updater.available() else []) + [
            ("◀▶", "More"), ("SELECT", "List"), ("L R", "Tabs"), ("B", "Home")]
        if self.kind in LISTEN_KINDS:
            hints.append(("START", "Now playing"))
        return hints

    def render_sysdash(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        n = self.sys_now or {}
        y = self.LIST_TOP + 10
        right = W - 20
        for word, colour, light in self.sysdash_says(n):   # (from the right: each a word and a light)
            w = d.textlength(word, font=F["label"]) + 30
            d.rounded_rectangle((right - w, y - 11, right, y + 11), radius=11, fill=ROW)
            d.ellipse((right - w + 10, y - 4, right - w + 18, y + 4), fill=light)
            d.text((right - w + 24, y), word, font=F["label"], fill=colour, anchor="lm")
            right -= w + 8
        board = n.get("board") or n.get("host") or "This Pi"
        d.text((20, y), self.fit(d, board, F["small"], right - 32), font=F["small"], fill=MUTED, anchor="lm")
        top, bottom = self.LIST_TOP + 28, H - self.FOOTER - 6
        rows = 5 if bottom - top >= 370 else 4
        tiles_h = 66
        panel_h = 24 + rows * 22
        chart_top = top + tiles_h + 14
        plot_h = max(48, bottom - chart_top - 14 - 22 - 12 - panel_h)
        self.sysdash_tiles(d, n, top, tiles_h)
        self.sysdash_chart(d, n, chart_top, plot_h)
        self.sysdash_panel(d, n, chart_top + 14 + plot_h + 22 + 12, rows)
        self.footer(d, self.sysdash_hints())
        self.fb.show(img)

    def sysdash_says(self, n):
        """What the top right says, right to left: the power (a light that's green or red), and a newer Pietato."""
        out = []
        text, bad = n.get("power") or ("unknown", False)
        if bad:
            now = text[len("Now: "):] if text.startswith("Now: ") else text
            out.append((now[:1].upper() + now[1:], WARN, WARN))
        elif text.startswith("OK"):
            out.append(("Power OK", TEXT, DONE))
        up = self.updater
        if up.available():                             # (Update software's in the list: SELECT)
            out.append(("New version" if up.new > 0 else "Finish updating", TEXT, ACCENT))
        return out

    def sysdash_tiles(self, d, n, top, h):
        """Its four numbers, each with a meter under it of the same (red when it's too hot, or the SD card's nearly
        full)."""
        F, W = self.fonts, self.fb.w
        t, busy, mem, disk = n.get("temp"), n.get("busy"), n.get("mem"), n.get("disk")
        hot = t is not None and t >= HOT_C
        full = bool(disk) and disk[1] < 1 << 30
        where = "disk" if is_pc() else "card"           # (a Pi's SD card; a PC's disk)
        tiles = [
            (["CPU temperature", "Temperature", "Temp"], f"{t:.1f} °C" if t is not None else "—",
             None if t is None else t / TEMP_FULL, SD_TEMP, hot),
            (["CPU busy", "CPU"], f"{busy:.0f}%" if busy is not None else "…",
             None if busy is None else busy / 100, SD_CPU, False),
            ([f"Memory used of {short_size(mem[1])}", "Memory used", "Memory"] if mem else ["Memory"],
             short_size(mem[0]) if mem else "—", mem[0] / mem[1] if mem else None, SD_MEM, False),
            ([f"Free on the {where} of {short_size(disk[2])}", f"Free on the {where}", "Storage free", "Free"]
             if disk else ["Storage"], short_size(disk[1]) if disk else "—",
             disk[1] / disk[2] if disk and disk[2] else None, SD_DISK, full),
        ]
        gap = 8
        tw = (W - 24 - gap * (len(tiles) - 1)) / len(tiles)
        for k, (labels, value, part, colour, warn) in enumerate(tiles):
            x0 = 12 + k * (tw + gap)
            x1 = x0 + tw
            d.rounded_rectangle((x0, top, x1, top + h), radius=10, fill=ROW)
            label = next((s for s in labels if d.textlength(s, font=F["label"]) <= tw - 24), labels[-1])
            d.text((x0 + 12, top + 16), label, font=F["label"], fill=MUTED, anchor="lm")
            d.text((x0 + 12, top + 39), self.fit(d, value, F["big"], tw - 24), font=F["big"],
                   fill=WARN if warn else TEXT, anchor="lm")
            if part is not None:                       # (the meter: its colour on a darker track)
                part = max(0.0, min(1.0, part))
                y0 = top + h - 11
                d.rounded_rectangle((x0 + 12, y0, x1 - 12, y0 + 4), radius=2, fill=PH_AXIS)
                if part > 0:
                    d.rounded_rectangle((x0 + 12, y0, x0 + 12 + max(4, (x1 - x0 - 24) * part), y0 + 4), radius=2,
                                        fill=WARN if warn else colour)

    def sysdash_recent(self, which):
        """The last 5 minutes' looks at one of the CPU's numbers (1: how busy, 2: how hot): [(seconds before the
        newest, value)], the newest last. [] before there are any."""
        got = [(s[0], s[which]) for s in self.sys_history.samples if s[which] is not None]
        if not got:
            return []
        newest = got[-1][0]
        span = HISTORY_EVERY * (HISTORY_KEEP - 0.5)
        return [(newest - t, v) for t, v in got if newest - t <= span and time.monotonic() - t <= span + HISTORY_EVERY]

    def sysdash_chart(self, d, n, top, plot_h):
        """How busy the CPU's been the last 5 minutes: a column every 10 seconds, the newest on the right."""
        F, W = self.fonts, self.fb.w
        d.text((16, top), "CPU busy, last 5 minutes", font=F["label"], fill=MUTED, anchor="lm")
        if n.get("mhz"):
            d.text((W - 16, top), f"{n['mhz']} MHz now", font=F["label"], fill=BODY, anchor="rm")
        y0, y1 = top + 14, top + 14 + plot_h            # (the plot)
        x0, x1 = 50, W - 16
        d.line((x0, y0, x1, y0), fill=LINE)             # (its top, and its baseline: hairlines)
        d.line((x0, y1, x1, y1), fill=PH_AXIS)
        d.text((x0 - 8, y0), "100%", font=F["badge"], fill=MUTED, anchor="rm")
        d.text((x0 - 8, y1), "0", font=F["badge"], fill=MUTED, anchor="rm")
        slot = (x1 - x0) / HISTORY_KEEP
        d.text((x0 + slot / 2, y1 + 11), "5 MIN AGO", font=F["badge"], fill=MUTED, anchor="lm")
        d.text((x1 - slot / 2, y1 + 11), "NOW", font=F["badge"], fill=MUTED, anchor="rm")
        got = self.sysdash_recent(1)
        if not got:
            d.text(((x0 + x1) / 2, (y0 + y1) / 2), "A column every 10 seconds, from now", font=F["label"],
                   fill=MUTED, anchor="mm")
            return
        bw = max(2, min(24, slot - 4))
        for ago, busy in got:
            k = HISTORY_KEEP - 1 - int(round(ago / HISTORY_EVERY))
            hb = plot_h * busy / 100
            if k >= 0 and hb >= 1:                     # (rounded at its top, square on the baseline)
                cx = x0 + slot * (k + 0.5)
                self.pihole_bar(d, (cx - bw / 2, y1 - hb, cx + bw / 2, y1), SD_CPU)

    def sysdash_panel(self, d, n, top, rows):
        """Below the chart, ◀▶: the network, the temperature the last 5 minutes, this Pi, what Pietato's busy with."""
        F, W = self.fonts, self.fb.w
        key, title = SD_PANELS[self.sys_panel % len(SD_PANELS)]
        d.text((16, top), on_pc(title), font=F["label"], fill=MUTED, anchor="lm")   # (a PC's: This PC)
        for k in range(len(SD_PANELS)):                 # (which of them this is)
            cx = W - 16 - (len(SD_PANELS) - 1 - k) * 14
            on = k == self.sys_panel % len(SD_PANELS)
            r = 4 if on else 3
            d.ellipse((cx - r, top - r, cx + r, top + r), fill=TEXT if on else PH_AXIS)
        y = top + 24
        if key == "temp":
            return self.sysdash_temp(d, y, rows)
        lines = self.sysdash_lines(key, n)[:rows]
        if not lines:
            d.text((16, y + 8), "Nothing, now", font=F["label"], fill=MUTED, anchor="lm")
            return
        name_w = max(d.textlength(label, font=F["label"]) for label, *_ in lines)
        vx = 16 + name_w + 24                          # (where a value's room starts)
        for i, (label, value, part, colour) in enumerate(lines):
            cy = y + i * 22 + 8
            d.text((16, cy), label, font=F["label"], fill=BODY, anchor="lm")
            if part is not None:                       # (a bar, then the number at the end)
                bx1 = W - 16 - max(70, d.textlength(value, font=F["label"]) + 14)
                self.pihole_bar_h(d, (vx, cy - 4, vx + max(3, (bx1 - vx) * max(0.0, min(1.0, part))), cy + 4),
                                  colour)
                d.text((W - 16, cy), value, font=F["label"], fill=TEXT, anchor="rm")
            else:
                d.text((W - 16, cy), self.fit(d, value, F["label"], W - 16 - vx), font=F["label"],
                       fill=colour, anchor="rm")

    def sysdash_lines(self, key, n):
        """A panel's lines: [(what, its value, how far a bar goes (0 to 1) or None, the colour)]."""
        if key == "network":
            out = []
            if n.get("ssid"):
                out.append(("WiFi", n["ssid"], None, TEXT))
            else:
                out.append(("WiFi", "Connected" if n.get("wifi_q") else "Not connected", None,
                            TEXT if n.get("wifi_q") else WARN))
            if n.get("dbm") is not None:
                lo, hi = SIGNAL_RANGE
                out.append(("Signal", f"{n['dbm']} dBm", (n["dbm"] - lo) / (hi - lo), SD_MEM))
            out.append(("IP address", n.get("ip") or "None", None, TEXT if n.get("ip") else MUTED))
            out.append(("Hostname", n.get("host") or "", None, TEXT))
            if n.get("ip"):
                out.append(("Web page", f"http://{n['ip']}:{WEB_PORT}", None, TEXT))
            return out
        if key == "pi":
            out = [(what, value, None, TEXT) for what, value in (
                ("Board", n.get("board")), ("System", n.get("os")), ("Kernel", n.get("kernel")),
                ("Up for", uptime_text(n["up"]) if n.get("up") is not None else None),
                ("CPU speed", f"{n['mhz']} MHz" if n.get("mhz") else None)) if value]
            return out
        out = []                                       # (in the background: how far each has got, and on what)
        for what, far in n.get("background") or ():
            m = re.match(r"(\d+)%\s*(?:·\s*)?(.*)", str(far))
            if m:
                out.append((what, f"{m.group(1)}%", int(m.group(1)) / 100, SD_CPU))
                if m.group(2):
                    out.append(("", m.group(2), None, MUTED))
            else:
                out.append((what, str(far), None, BODY))
        return out

    def sysdash_temp(self, d, top, rows):
        """The CPU's temperature the last 5 minutes: a line (red where it's too hot), what it is now at its end."""
        F, W = self.fonts, self.fb.w
        got = self.sysdash_recent(2)
        if len(got) < 2:
            d.text((16, top + 8), "A look every 10 seconds, from now", font=F["label"], fill=MUTED, anchor="lm")
            return
        temps = [c for _, c in got]
        lo, hi = int(min(temps)) - 1, int(max(temps)) + 2
        if hi - lo < 6:                                 # (a calm one isn't drawn as a storm)
            lo, hi = lo - (6 - (hi - lo)) // 2, hi + (6 - (hi - lo) + 1) // 2
        h = rows * 22 - 10
        y0, y1 = top - 4, top - 4 + h
        now = f"{temps[-1]:.1f} °C"
        x0, x1 = 50, W - 16 - d.textlength(now, font=F["label"]) - 14
        d.line((x0, y0, x1, y0), fill=LINE)
        d.line((x0, y1, x1, y1), fill=PH_AXIS)
        d.text((x0 - 8, y0), f"{hi}°", font=F["badge"], fill=MUTED, anchor="rm")
        d.text((x0 - 8, y1), f"{lo}°", font=F["badge"], fill=MUTED, anchor="rm")
        span = HISTORY_EVERY * (HISTORY_KEEP - 1)
        pts = [(x1 - (x1 - x0) * min(ago, span) / span, y1 - h * (c - lo) / (hi - lo), c) for ago, c in got]
        for (xa, ya, ca), (xb, yb, cb) in zip(pts, pts[1:]):
            d.line((xa, ya, xb, yb), fill=WARN if max(ca, cb) >= HOT_C else SD_TEMP, width=2)
        x, y, c = pts[-1]
        colour = WARN if c >= HOT_C else SD_TEMP
        d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=colour)
        d.text((W - 16, y), now, font=F["label"], fill=WARN if c >= HOT_C else TEXT, anchor="rm")
