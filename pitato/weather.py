"""The weather (Open-Meteo, free with no key, and the US Weather Service), and finding where you are."""
import json
import os
import threading
import time
import urllib.parse

from .config import CACHE_DIR
from .util import fetch_json


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WHERE_AM_I = [   # where your internet address says you are (the same ones PiE-ink asks)
    ("https://ipapi.co/json/", lambda d: (d.get("latitude"), d.get("longitude"), d.get("city"),
                                          d.get("region"), d.get("country_code"))),
    ("https://ipwho.is/", lambda d: (d.get("latitude"), d.get("longitude"), d.get("city"),
                                     d.get("region"), d.get("country_code"))),
    ("http://ip-api.com/json/?fields=status,lat,lon,city,regionName,countryCode",
     lambda d: (d.get("lat"), d.get("lon"), d.get("city"), d.get("regionName"), d.get("countryCode"))),
]


def place_text(loc):
    if not loc:
        return "Not set"
    bits = [loc.get("name")]
    if loc.get("admin") and loc.get("admin") != loc.get("name"):
        bits.append(loc["admin"])
    return ", ".join(b for b in bits if b)


def geocode(name):
    q = urllib.parse.urlencode({"name": name, "count": 8, "language": "en", "format": "json"})
    out = []
    for r in (fetch_json(f"{GEOCODE_URL}?{q}") or {}).get("results") or []:
        out.append({"name": r.get("name", ""), "admin": r.get("admin1", ""),
                    "country": r.get("country_code", ""), "lat": r.get("latitude"),
                    "lon": r.get("longitude")})
    return out


def find_me():
    """Where your internet address says you are, or None."""
    for url, pick in WHERE_AM_I:
        try:
            lat, lon, city, region, cc = pick(fetch_json(url))
            if lat is not None and lon is not None:
                return {"name": city or "Here", "admin": region or "", "country": cc or "",
                        "lat": float(lat), "lon": float(lon)}
        except Exception:
            continue
    return None


# ---- weather: Open-Meteo (free, no key), like PiE-ink ----------------------------------
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
NWS_POINTS = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
WEATHER_TTL = 600
WX_CODES = {   # WMO weather codes -> (words, kind)
    0: ("Clear", "clear"), 1: ("Mostly clear", "clear"), 2: ("Partly cloudy", "cloud"), 3: ("Overcast", "cloud"),
    45: ("Fog", "fog"), 48: ("Icy fog", "fog"),
    51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"), 57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Showers", "rain"), 81: ("Showers", "rain"), 82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Thunderstorm, hail", "storm"), 99: ("Thunderstorm, hail", "storm"),
}
WX_TINT = {   # PiE-ink's colours for each kind of weather (on a dark screen)
    "sun": (255, 200, 60), "moon": (205, 215, 240), "cloud": (195, 200, 210), "dark": (150, 156, 168),
    "rain": (90, 160, 255), "snow": (215, 235, 255), "bolt": (245, 200, 80), "fog": (175, 180, 190),
    "wind": (195, 200, 210), "sunset": (255, 150, 80),
}


def wx_words(code):
    try:
        return WX_CODES.get(int(code), ("—", "cloud"))
    except (TypeError, ValueError):
        return ("—", "cloud")


def wx_icon_name(code, is_day=True):
    words, kind = wx_words(code)
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = 3
    if kind == "clear":
        return ("sun" if is_day else "moon") if code == 0 else ("partly_day" if is_day else "partly_night")
    if kind == "cloud":
        return "overcast" if code == 3 else ("partly_day" if is_day else "partly_night")
    if kind == "rain":
        return "heavyrain" if code in (55, 57, 65, 67, 82) else "rain"
    return kind                                   # fog, snow, storm


def compass(degrees):
    try:
        return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((float(degrees) + 22.5) // 45) % 8]
    except (TypeError, ValueError):
        return ""


def draw_wx(name, size):
    """A weather picture, drawn three times bigger and scaled down for smooth edges."""
    from PIL import Image, ImageDraw
    S = size * 3
    k = S / 120
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    T = WX_TINT

    def B(x0, y0, x1, y1):
        return (x0 * k, y0 * k, x1 * k, y1 * k)

    def L(*pts):
        return [(x * k, y * k) for x, y in pts]

    def sun(cx, cy, r):
        import math
        for t in range(8):
            a = math.radians(t * 45)
            d.line(L((cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35),
                     (cx + math.cos(a) * r * 1.75, cy + math.sin(a) * r * 1.75)),
                   fill=T["sun"], width=max(1, int(r * 0.22 * k)))
        d.ellipse(B(cx - r, cy - r, cx + r, cy + r), fill=T["sun"])

    def moon(cx, cy, r):
        d.ellipse(B(cx - r, cy - r, cx + r, cy + r), fill=T["moon"])
        d.ellipse(B(cx - r * 0.35, cy - r * 1.15, cx + r * 1.45, cy + r * 0.65), fill=(0, 0, 0, 0))

    def cloud(x, y, w, colour):
        h = w * 0.5
        d.ellipse(B(x + w * 0.08, y + h * 0.35, x + w * 0.48, y + h * 1.0), fill=colour)
        d.ellipse(B(x + w * 0.26, y, x + w * 0.74, y + h * 0.95), fill=colour)
        d.ellipse(B(x + w * 0.56, y + h * 0.28, x + w * 0.94, y + h * 1.0), fill=colour)
        d.rounded_rectangle(B(x, y + h * 0.55, x + w, y + h * 1.12), radius=h * 0.28 * k, fill=colour)

    if name == "sun":
        sun(60, 60, 26)
    elif name == "moon":
        moon(58, 60, 34)
    elif name == "partly_day":
        sun(76, 42, 18)
        cloud(10, 46, 84, T["cloud"])
    elif name == "partly_night":
        moon(78, 40, 22)
        cloud(10, 46, 84, T["cloud"])
    elif name == "overcast":
        cloud(34, 20, 74, T["dark"])
        cloud(8, 44, 88, T["cloud"])
    elif name == "fog":
        for i, (x0, x1) in enumerate(((18, 102), (8, 92), (24, 108), (14, 84))):
            y = 34 + i * 16
            d.rounded_rectangle(B(x0, y, x1, y + 8), radius=4 * k, fill=T["fog"])
    elif name in ("rain", "heavyrain", "snow", "storm"):
        cloud(10, 14, 100, T["dark"] if name == "storm" else T["cloud"])
        if name == "storm":
            d.polygon(L((62, 64), (44, 94), (58, 94), (50, 116), (78, 82), (63, 82), (72, 64)), fill=T["bolt"])
        elif name == "snow":
            for x, y in ((34, 84), (60, 96), (86, 84), (46, 108), (74, 108)):
                d.ellipse(B(x - 5, y - 5, x + 5, y + 5), fill=T["snow"])
        else:
            drops = (30, 52, 74, 96) if name == "heavyrain" else (38, 62, 86)
            for x in drops:
                d.line(L((x, 76), (x - 8, 102)), fill=T["rain"], width=int(6 * k))
    elif name == "humidity":
        d.polygon(L((60, 14), (30, 70), (90, 70)), fill=T["rain"])
        d.ellipse(B(30, 46, 90, 106), fill=T["rain"])
    elif name == "wind":
        for y, w in ((36, 70), (60, 92), (84, 56)):
            d.line(L((14, y), (14 + w, y)), fill=T["wind"], width=int(9 * k))
            d.arc(B(14 + w - 14, y - 24, 14 + w + 14, y + 4), -90, 90, fill=T["wind"], width=int(9 * k))
    elif name in ("sunrise", "sunset"):
        col = T["sun"] if name == "sunrise" else T["sunset"]
        d.pieslice(B(28, 52, 92, 116), 180, 360, fill=col)
        d.line(L((10, 86), (110, 86)), fill=col, width=int(8 * k))
        tip, base = ((60, 8), 40) if name == "sunrise" else ((60, 44), 12)
        d.line(L((60, 12), (60, 42)), fill=col, width=int(8 * k))
        d.polygon(L((44, base + (0 if name == "sunrise" else 20)), (76, base + (0 if name == "sunrise" else 20)),
                    tip), fill=col)
    return im.resize((size, size), Image.LANCZOS)


class _Stale(Exception):
    pass


class Weather:
    """Now, the next hours and the week from Open-Meteo, and for US places the
    National Weather Service's worded forecast; fetched on a thread and kept on
    disk, so the last forecast shows (with its age) without WiFi. PiE-ink on
    another Pi is asked first: when its forecast is fresh and for here, the home
    screen (and the bot) use it. It has no hours and a shorter week, so the
    Weather tab gets the whole forecast itself."""

    def __init__(self, get_loc, get_units, pie=None):
        self.get_loc, self.get_units = get_loc, get_units
        self.pie = pie
        self.data, self.nws, self.t = None, [], 0.0
        self.src = ""                # "PiE-ink" when what's here came from it
        self.checked = 0.0           # when it was last looked for (PiE-ink asked, or the internet)
        self.error = None
        self.busy = False
        self.gen = 0                 # counted up as it starts over: a fetch begun before is for then (it's done again)
        self.on_change = lambda: None
        self.load_cache()

    def key(self):
        loc = self.get_loc()
        if not loc or loc.get("lat") is None:
            return None
        return f"{float(loc['lat']):.3f},{float(loc['lon']):.3f},{self.get_units()}"

    @property
    def cache_path(self):
        return os.path.join(CACHE_DIR, "weather.json")

    def load_cache(self):
        try:
            with open(self.cache_path) as f:
                c = json.load(f)
            if c.get("key") == self.key():
                self.data, self.nws, self.t = c.get("data"), c.get("nws") or [], c.get("t", 0.0)
                self.src = c.get("src") or ""
        except (OSError, ValueError):
            pass

    def save_cache(self, key):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(self.cache_path, "w") as f:
                json.dump({"key": key, "data": self.data, "nws": self.nws, "t": self.t, "src": self.src}, f)
        except OSError:
            pass

    def reset(self):
        self.gen += 1
        self.data, self.nws, self.t, self.error, self.src, self.checked = None, [], 0.0, None, "", 0.0
        self.load_cache()
        self.refresh(force=True)

    def partial(self):
        """What's here is PiE-ink's: no hours, a shorter week."""
        return bool(self.data) and not self.data.get("hours")

    def refresh(self, force=False, full=False):
        """Fetched again when it's old (full: the Weather tab, which wants the hours too)."""
        if self.busy or self.key() is None:
            return
        upgrade = full and self.partial()
        if not force:
            if not upgrade and time.time() - self.t < WEATHER_TTL:
                return
            if time.time() - self.checked < 60 and (self.error or not upgrade):
                return                                 # looked a moment ago
        self.busy = True
        threading.Thread(target=self.job, args=(full,), daemon=True, name="weather").start()

    def from_pie(self, key, loc, units, gen=None):
        """PiE-ink's forecast when it has one for here that isn't too old: taken when it's newer than
        what's here; otherwise its next one is waited for (it's asked again in a minute), as PiE-ink
        is keeping it fresh. True either way: False means the internet is asked."""
        try:
            got = self.pie.weather(loc, units) if self.pie is not None else None
        except Exception:
            got = None
        if not got or got["age"] >= WEATHER_TTL * 1.5:
            return False
        if time.time() - got["age"] <= self.t + 1:
            return True
        if key != self.key() or (gen is not None and gen != self.gen):
            raise _Stale()
        self.data, self.t, self.error, self.src = got["data"], time.time() - got["age"], None, "PiE-ink"
        if got["nws"]:
            self.nws = got["nws"]
        self.save_cache(key)
        return True

    def job(self, full=False):
        key, loc, units, gen = self.key(), self.get_loc(), self.get_units(), self.gen
        self.checked = time.time()
        try:
            if not full and self.from_pie(key, loc, units, gen):
                return
            params = {"latitude": loc["lat"], "longitude": loc["lon"], "timezone": "auto",
                      "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
                                 "wind_speed_10m,wind_direction_10m,is_day,precipitation",
                      "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
                      "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,"
                               "precipitation_probability_max",
                      "forecast_days": 7}
            if units == "F":
                params.update(temperature_unit="fahrenheit", wind_speed_unit="mph", precipitation_unit="inch")
            else:
                params.update(wind_speed_unit="kmh")
            d = fetch_json(WEATHER_URL + "?" + urllib.parse.urlencode(params))
            c, hr, dl = d.get("current") or {}, d.get("hourly") or {}, d.get("daily") or {}
            hours = []
            times = hr.get("time") or []
            now_hour = str(c.get("time", ""))[:13]
            start = next((i for i, t in enumerate(times) if t[:13] >= now_hour), 0) + 1
            for i in range(start, min(start + 8, len(times))):
                hours.append({"time": times[i], "temp": (hr.get("temperature_2m") or [None] * 999)[i],
                              "code": (hr.get("weather_code") or [None] * 999)[i],
                              "rain": (hr.get("precipitation_probability") or [None] * 999)[i],
                              "is_day": bool((hr.get("is_day") or [1] * 999)[i])})
            days = []
            for i, day in enumerate(dl.get("time") or []):
                def col(name, default=None):
                    v = dl.get(name) or []
                    return v[i] if i < len(v) else default
                days.append({"date": day, "code": col("weather_code"), "hi": col("temperature_2m_max"),
                             "lo": col("temperature_2m_min"), "rain": col("precipitation_probability_max"),
                             "sunrise": str(col("sunrise", ""))[-5:], "sunset": str(col("sunset", ""))[-5:]})
            if key != self.key() or gen != self.gen:   # the place or units changed meanwhile (or it started over)
                raise _Stale()
            self.data = {"temp": c.get("temperature_2m"), "feels": c.get("apparent_temperature"),
                         "humidity": c.get("relative_humidity_2m"), "wind": c.get("wind_speed_10m"),
                         "wind_dir": c.get("wind_direction_10m"), "code": c.get("weather_code"),
                         "is_day": bool(c.get("is_day", 1)), "units": units, "hours": hours, "days": days}
            self.t, self.error, self.src = time.time(), None, ""
            if str(loc.get("country", "")).upper() == "US":
                try:
                    pt = fetch_json(NWS_POINTS.format(lat=float(loc["lat"]), lon=float(loc["lon"])))
                    fc = fetch_json(pt["properties"]["forecast"])
                    self.nws = [[p.get("name", ""), p.get("detailedForecast", "")]
                                for p in fc["properties"]["periods"][:6]]
                except Exception:
                    pass
            if key == self.key() and gen == self.gen:
                self.save_cache(key)
        except _Stale:
            self.t = 0.0
        except Exception:
            self.error = "Can't reach the weather service"
            if not self.data:
                self.t = time.time()
        finally:
            self.busy = False
            self.on_change()
            if key != self.key() or gen != self.gen:
                self.refresh(force=True)               # for where you are now
