"""The Weather tab."""
import textwrap
import threading
import time

from ..theme import ACCENT, BODY, LINE, MUTED, ROW, TEXT, WARN
from ..weather import compass, draw_wx, place_text, wx_icon_name, WX_TINT, wx_words


class WeatherScreen:
    """The Weather tab."""

    def weather_changed(self):
        """Location or units changed: the weather starts over."""
        w = getattr(self, "weather", None)
        if w is not None:
            w.reset()

    # -- Weather ---------------------------------------------------------------
    def weather_drawn(self):
        if self.active and (self.view == "home" or (self.view == "list" and self.tab_type() == "weather")):
            self.dirty = True

    def wx_pages(self):
        return ["Now", "Week"] + (["Forecast"] if self.weather.nws else [])

    def press_weather(self, name, repeat):
        if name in ("left", "right") and not repeat:
            n = len(self.wx_pages())
            self.wx_page = (self.wx_page + (1 if name == "right" else -1)) % n
        elif name == "x" and not repeat:
            self.weather.refresh(force=True, full=True)
            self.toast("Refreshing", 2)
        elif name == "a" and not repeat and not self.setting("location"):
            self.loc_status = None
            self.toast("Finding you…", 3)
            threading.Thread(target=self.locate_job, args=(None,), daemon=True).start()
        self.dirty = True
        return None

    def wx_icon(self, name, size):
        key = (name, size)
        if key not in self.wx_icons:
            self.wx_icons[key] = draw_wx(name, size)
        return self.wx_icons[key]

    def deg(self, v):
        try:
            return f"{round(float(v))}°"
        except (TypeError, ValueError, OverflowError):
            return "—"

    def hour_label(self, stamp):
        try:
            t = time.strptime(stamp, "%Y-%m-%dT%H:%M")
        except ValueError:
            return ""
        if self.setting("clock") == "24-hour":
            return time.strftime("%H:00", t)
        return time.strftime("%-I %p", t)

    def render_weather(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        wx, loc = self.weather.data, self.setting("location")
        top = self.LIST_TOP
        if not loc:
            self.empty_state(d, "Where are you?", "A finds you from your internet address, or set a town in Settings")
            self.footer(d, [("A", "Find me"), ("L R", "Tabs"), ("B", "Home")])
            self.fb.show(img)
            return
        if not wx:
            if self.weather.error:
                self.empty_state(d, "Can't reach the weather service", "Check the WiFi; X tries again")
            else:
                self.empty_state(d, "Getting the weather", place_text(loc))
            self.footer(d, [("X", "Refresh"), ("L R", "Tabs"), ("B", "Home")])
            self.fb.show(img)
            return
        pages = self.wx_pages()
        self.wx_page %= len(pages)
        page = pages[self.wx_page]
        d.text((24, top + 12), place_text(loc).upper(), font=F["small"], fill=MUTED, anchor="lm")
        age = time.time() - self.weather.t
        when = ("Updated just now" if age < 90 else f"Updated {int(age // 60)} min ago" if age < 3600
                else f"Updated {int(age // 3600)} h ago")
        d.text((W - 24, top + 12), when, font=F["small"], fill=WARN if age > 3 * 3600 else MUTED, anchor="rm")
        today = (wx.get("days") or [{}])[0]

        if page == "Now":
            name = wx_icon_name(wx.get("code"), wx.get("is_day", True))
            icon = self.wx_icon(name, 128)
            img.paste(icon, (W - 32 - 128, top + 22), icon)
            d.text((22, top + 18), self.deg(wx.get("temp")), font=F["temp"], fill=TEXT, anchor="la")
            d.text((26, top + 100), wx_words(wx.get("code"))[0], font=F["big"], fill=TEXT, anchor="la")
            d.text((26, top + 130), f"Feels like {self.deg(wx.get('feels'))}   ·   "
                   f"High {self.deg(today.get('hi'))}   Low {self.deg(today.get('lo'))}",
                   font=F["small"], fill=BODY, anchor="la")
            row = []
            if wx.get("humidity") is not None:
                row.append(("humidity", f"{round(float(wx['humidity']))}%"))
            if wx.get("wind") is not None:
                unit = "mph" if wx.get("units") == "F" else "km/h"
                row.append(("wind", f"{round(float(wx['wind']))} {unit} {compass(wx.get('wind_dir'))}".strip()))
            if today.get("rain") is not None:
                row.append(("rain", f"{today['rain']}% rain"))
            if today.get("sunrise"):
                row.append(("sunrise", self.hour_min(today["sunrise"])))
            if today.get("sunset"):
                row.append(("sunset", self.hour_min(today["sunset"])))
            x, y = 26, top + 162
            for ic, text in row:
                pic = self.wx_icon(ic, 20)
                img.paste(pic, (int(x), int(y) - 10), pic)
                x += 26
                d.text((x, y), text, font=F["small"], fill=BODY, anchor="lm")
                x += d.textlength(text, font=F["small"]) + 20
            # the next hours (on a taller screen than the GPi Case's, these and the days lower down)
            more = max(0, H - 480) // 3
            y0 = top + 178 + more
            d.line((20, y0, W - 20, y0), fill=LINE)
            hours = (wx.get("hours") or [])[:8]
            if not hours and self.weather.busy:            # (PiE-ink's forecast has none: on their way)
                d.text((W / 2, y0 + 41), "Getting the next hours…", font=F["small"], fill=MUTED, anchor="mm")
            if hours:
                cw = (W - 40) / len(hours)
                for i, h in enumerate(hours):
                    cx = 20 + cw * i + cw / 2
                    d.text((cx, y0 + 14), self.hour_label(h["time"]), font=F["label"], fill=MUTED, anchor="mm")
                    pic = self.wx_icon(wx_icon_name(h.get("code"), h.get("is_day", True)), 32)
                    img.paste(pic, (int(cx - 16), int(y0 + 24)), pic)
                    d.text((cx, y0 + 68), self.deg(h.get("temp")), font=F["small_b"], fill=TEXT, anchor="mm")
            # the coming days
            y1 = y0 + 82 + more
            d.line((20, y1, W - 20, y1), fill=LINE)
            days = (wx.get("days") or [])[1:7]
            if days:
                cw = (W - 40) / len(days)
                for i, day in enumerate(days):
                    cx = 20 + cw * i + cw / 2
                    try:
                        label = time.strftime("%a", time.strptime(day["date"], "%Y-%m-%d"))
                    except (ValueError, KeyError):
                        label = "—"
                    d.text((cx, y1 + 13), label, font=F["label"], fill=MUTED, anchor="mm")
                    pic = self.wx_icon(wx_icon_name(day.get("code"), True), 28)
                    img.paste(pic, (int(cx - 14), int(y1 + 22)), pic)
                    hi, lo = self.deg(day.get("hi")), self.deg(day.get("lo"))
                    tw = d.textlength(hi, font=F["small_b"]) + 6 + d.textlength(lo, font=F["label"])
                    d.text((cx - tw / 2, y1 + 60), hi, font=F["small_b"], fill=TEXT, anchor="lm")
                    d.text((cx - tw / 2 + d.textlength(hi, font=F["small_b"]) + 6, y1 + 60), lo,
                           font=F["label"], fill=MUTED, anchor="lm")
        elif page == "Week":
            rh = 44 + max(0, H - 480) // 8                # (a taller screen: taller rows)
            for i, day in enumerate((wx.get("days") or [])[:7]):
                y = top + 30 + i * rh
                if y + rh > H - self.FOOTER:
                    break
                try:
                    label = "Today" if i == 0 else time.strftime("%A", time.strptime(day["date"], "%Y-%m-%d"))
                except (ValueError, KeyError):
                    label = "—"
                if i % 2 == 0:
                    d.rounded_rectangle((12, y + 2, W - 12, y + rh - 2), radius=8, fill=ROW)
                mid = y + rh / 2
                d.text((26, mid), label, font=F["row"], fill=TEXT, anchor="lm")
                pic = self.wx_icon(wx_icon_name(day.get("code"), True), 30)
                img.paste(pic, (150, int(mid - 15)), pic)
                d.text((194, mid), wx_words(day.get("code"))[0], font=F["small"], fill=BODY, anchor="lm")
                if day.get("rain"):
                    d.text((W - 150, mid), f"{day['rain']}%", font=F["small"], fill=WX_TINT["rain"], anchor="rm")
                d.text((W - 80, mid), self.deg(day.get("hi")), font=F["row_b"], fill=TEXT, anchor="rm")
                d.text((W - 26, mid), self.deg(day.get("lo")), font=F["row"], fill=MUTED, anchor="rm")
        else:                                          # the NWS in its own words
            y = top + 30
            for name, text in self.weather.nws:
                if y > H - self.FOOTER - 40:
                    break
                d.text((24, y), name, font=F["small_b"], fill=ACCENT, anchor="la")
                y += 22
                for line in textwrap.wrap(text, 70)[:3]:
                    d.text((24, y), line, font=F["small"], fill=BODY, anchor="la")
                    y += 20
                y += 8
        # which page
        gap = 14
        x = W / 2 - (len(pages) - 1) * gap / 2
        for k in range(len(pages)):
            on = k == self.wx_page
            r = 4 if on else 3
            d.ellipse((x - r, H - self.FOOTER - 10 - r, x + r, H - self.FOOTER - 10 + r),
                      fill=TEXT if on else LINE)
            x += gap
        nxt = pages[(self.wx_page + 1) % len(pages)]
        self.footer(d, [("◀▶", nxt), ("X", "Refresh"), ("L R", "Tabs"), ("B", "Home")],
                    right="from Open-Meteo" + (" + NWS" if page == "Forecast" else ""))
        self.fb.show(img)
