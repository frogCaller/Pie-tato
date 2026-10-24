"""Internet radio: free stations from the Radio Browser directory, and your own in static/radio.txt."""
import random
import re
import socket
import urllib.parse

from .util import fetch_json, item


# ---- internet radio: free stations, plus anything in static/radio.txt -------
RADIO_STATIONS = [
    ("Radio Paradise", "eclectic mix", "http://stream.radioparadise.com/mp3-128"),
]
# Real stations from Radio Browser (radio-browser.info): a free, open directory of ~50,000
# stations' own streams. Each genre is the busiest stations across a few of its tags.
RADIO_GENRES = [
    ("Pop & Top 40", "POP", ["pop", "top 40", "hits"]),
    ("Hip-hop & R&B", "HIP", ["hip hop", "hiphop", "rnb"]),
    ("Rock", "ROCK", ["rock", "classic rock"]),
    ("Alternative & Indie", "ALT", ["alternative", "indie"]),
    ("Country", "CTRY", ["country"]),
    ("Latin", "LAT", ["latin", "reggaeton"]),
    ("Dance & EDM", "EDM", ["dance", "edm", "house"]),
    ("80s", "80S", ["80s"]),
    ("90s", "90S", ["90s"]),
    ("Oldies", "OLD", ["oldies", "70s", "60s"]),
    ("Jazz & Soul", "JAZZ", ["jazz", "soul"]),
    ("Reggae", "REGG", ["reggae"]),
    ("K-pop & J-pop", "KPOP", ["kpop", "k-pop", "jpop"]),
    ("Classical", "CLAS", ["classical"]),
    ("Lo-fi & chill", "LOFI", ["lofi", "lo-fi", "chillout"]),
]
RADIO_TTL = 86400                  # a genre's list is fetched again after a day
NOT_MUSIC = {"news", "talk", "sport", "sports", "podcast", "religious", "christian talk", "politics"}
_RB_HOSTS = []


def rb_hosts():
    """Radio Browser's servers, the way it asks: the names behind all.api.radio-browser.info."""
    if not _RB_HOSTS:
        names = []
        try:
            for info in socket.getaddrinfo("all.api.radio-browser.info", 443, proto=socket.IPPROTO_TCP):
                try:
                    name = socket.gethostbyaddr(info[4][0])[0]
                except OSError:
                    continue
                if name.endswith("radio-browser.info") and name not in names:
                    names.append(name)
        except OSError:
            pass
        random.shuffle(names)
        _RB_HOSTS.extend(names or ["de1.api.radio-browser.info", "de2.api.radio-browser.info",
                                   "fi1.api.radio-browser.info"])
    return list(_RB_HOSTS)


def rb_get(path, params=None):
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    last = None
    for host in rb_hosts():
        try:
            out = fetch_json(f"https://{host}{path}{q}")
            if _RB_HOSTS and _RB_HOSTS[0] != host:      # remember the one that answered
                _RB_HOSTS.remove(host)
                _RB_HOSTS.insert(0, host)
            return out
        except Exception as ex:
            last = ex
    raise last or OSError("no Radio Browser server")


def rb_stations(tags=(), country="", name="", limit=40):
    """The busiest working music stations for some tags, a country or a name."""
    base = {"order": "clickcount", "reverse": "true", "hidebroken": "true", "limit": 80}
    if country:
        base["countrycode"] = country
    queries = [dict(base, tag=t, tagExact="true") for t in tags] or [dict(base, name=name) if name else base]
    found = []
    for q in queries:
        try:
            found += rb_get("/json/stations/search", q) or []
        except Exception:
            if not found and q is queries[-1]:
                raise
    out, seen = [], set()
    for st in sorted(found, key=lambda x: -int(x.get("clickcount") or 0)):
        url = (st.get("url_resolved") or st.get("url") or "").strip()
        title = re.sub(r"\s+", " ", st.get("name") or "").strip()
        tags_ = [t.strip() for t in (st.get("tags") or "").lower().split(",") if t.strip()]
        if (not url or not title or st.get("hls") in (1, "1") or "://" not in url
                or url.split("?")[0].lower().endswith((".m3u8", ".pls", ".m3u", ".asx"))
                or (st.get("codec") or "MP3").upper() not in ("MP3", "AAC", "AAC+", "OGG", "UNKNOWN")
                or set(tags_) & NOT_MUSIC):
            continue
        key = title.lower()
        if key in seen or url in seen:
            continue
        seen.update((key, url))
        sub = " · ".join(x for x in ((st.get("countrycode") or "").upper(),
                                     next((t for t in tags_ if t not in ("music",)), "")) if x)
        it = item("rb:" + (st.get("stationuuid") or url), title[:60], "radio", url, sub=sub)
        it["uuid"] = st.get("stationuuid") or ""
        logo = (st.get("favicon") or "").strip()
        it["logo"] = logo if logo.startswith(("https://", "http://")) else ""   # (for the web page)
        out.append(it)
        if len(out) >= limit:
            break
    return out
