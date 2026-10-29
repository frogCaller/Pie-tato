"""The TV remote and the lights, through Home Assistant."""
import json
import re
import threading
import time
import urllib.error
import urllib.request

from .config import edit_config, read_config


HA_POLL = 3              # seconds between asking Home Assistant how the TV is
HA_HELD = 0.3            # seconds between repeats while an arrow is held on the TV Remote
HA_WATCH = 30            # seconds to see a TV turn on or off (asking every second) before saying it didn't
HA_WAKE_AGAIN = 8        # ...asking it to turn on again this often meanwhile (a Samsung's or an LG's Wake-on-LAN,
WAKE_AGAIN = ("samsung", "lg")    # which is how Home Assistant wakes them, can go astray)
HA_LIGHTS_POLL = 5       # ...and how the lights are (all of Home Assistant's states, each time)
LIGHT_STEP = 10          # percent brighter or dimmer for each press
HA_FILE = "homeassistant.txt"
HA_HEAD = ("# Home Assistant, for the TV Remote and Lights: Pietato writes this when you set it up (Home Assistant's\n"
           "# settings, or the web page's). Keep it private: it has your token. Also, if you like:\n"
           "#   tv = media_player.living_room_tv     remote = remote.living_room_tv     style = samsung\n"
           "#   lights = light.kitchen, switch.fan_plug     (found by themselves when they're not here)\n")
HA_GUESS = "homeassistant.local:8123"   # where Home Assistant usually is, to start the address with


# The TV's own buttons, by how its Home Assistant integration names them. Samsung,
# Android/Google TV, Roku and Apple TV take them through remote.send_command;
# LG webOS through webostv.button on the TV itself.
TV_KEYS = {
    "samsung": {"up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT", "right": "KEY_RIGHT",
                "ok": "KEY_ENTER", "back": "KEY_RETURN", "home": "KEY_HOME",
                "chup": "KEY_CHUP", "chdown": "KEY_CHDOWN", "last": "KEY_PRECH", "guide": "KEY_GUIDE",
                "enter": "KEY_ENTER", "dash": "KEY_PLUS100", **{str(n): f"KEY_{n}" for n in range(10)}},
    "android": {"up": "DPAD_UP", "down": "DPAD_DOWN", "left": "DPAD_LEFT", "right": "DPAD_RIGHT",
                "ok": "DPAD_CENTER", "back": "BACK", "home": "HOME",
                "chup": "CHANNEL_UP", "chdown": "CHANNEL_DOWN", "last": "LAST_CHANNEL", "guide": "GUIDE",
                "enter": "ENTER", "dash": "MINUS", **{str(n): str(n) for n in range(10)}},
    "roku": {"up": "up", "down": "down", "left": "left", "right": "right",
             "ok": "select", "back": "back", "home": "home",
             "chup": "channel_up", "chdown": "channel_down", "enter": "enter"},
    "apple": {"up": "up", "down": "down", "left": "left", "right": "right",
              "ok": "select", "back": "menu", "home": "home"},
    "lg": {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
           "ok": "ENTER", "back": "BACK", "home": "HOME",
           "chup": "CHANNELUP", "chdown": "CHANNELDOWN", "guide": "GUIDE", "enter": "ENTER", "dash": "DASH",
           **{str(n): str(n) for n in range(10)}},
}
# the number pad: (label, what it does)
TV_PAD = [[("1", "1"), ("2", "2"), ("3", "3"), ("CH +", "chup")],
          [("4", "4"), ("5", "5"), ("6", "6"), ("CH −", "chdown")],
          [("7", "7"), ("8", "8"), ("9", "9"), ("Last", "last")],
          [("–", "dash"), ("0", "0"), ("⌫", "del"), ("Guide", "guide")],
          [("Go to channel", "go")]]
TV_STYLE_WORDS = [({"samsung", "tizen", "frame"}, "samsung"), ({"roku"}, "roku"),
                  ({"apple", "appletv"}, "apple"), ({"lg", "webos"}, "lg"),
                  ({"android", "google", "shield", "chromecast", "bravia", "sony", "philips",
                    "hisense", "tcl", "fire", "firetv"}, "android")]
TV_WORDS = {"tv", "television", "samsung", "lg", "bravia", "roku", "webos"}
TV_OFF = ("off", "standby", "unavailable")      # a TV that's off, as Home Assistant says (or that it can't reach)


def tv_power(state):
    """'on' or 'off', as Home Assistant says the TV is; None while it doesn't know."""
    if state in TV_OFF:
        return "off"
    return None if state in (None, "", "unknown") else "on"


def words(st):
    """The words in an entity's id and name, for matching a TV with its remote and its kind."""
    text = (st.get("entity_id", "") + " " + str(st.get("attributes", {}).get("friendly_name", "")))
    return set(re.split(r"[^a-z0-9]+", text.lower()))


def entity_list(text):
    """media_player.a, media_player.b (commas or spaces between)."""
    return [x for x in re.split(r"[,\s]+", text or "") if x]


def ha_url(text):
    """Home Assistant's address as you might write it (homeassistant.local:8123, .../api) as a URL."""
    url = (text or "").strip().rstrip("/")
    if url.endswith("/api"):
        url = url[:-4]
    if url and "://" not in url:
        url = "http://" + url
    return url


def save_ha(updates):
    """Home Assistant's address, token and the rest (as {"url": ..., "token": ...}) into homeassistant.txt, the rest of
    it kept: yours only, and never shown on the web page."""
    return edit_config(HA_FILE, updates, head=HA_HEAD, limit=600, private=True)


def ha_check(url, token, timeout=8):
    """Whether Home Assistant at url takes token: (True, its name and version in words) or (False, why not)."""
    url = ha_url(url)
    if not url:
        return False, "Home Assistant's address isn't set"
    if not token:
        return False, "The token isn't set"
    ha = HomeAssistant()
    ha.url, ha.token = url, token
    try:
        ha.call("GET", "/api/", timeout=timeout)
    except Exception as ex:
        return False, ha.why(ex)
    try:
        cfg = ha.call("GET", "/api/config", timeout=timeout) or {}
    except Exception:
        cfg = {}
    name = str(cfg.get("location_name") or "Home Assistant").strip()[:40]
    version = str(cfg.get("version") or "").strip()[:20]
    return True, f"Connected to {name}" + (f" ({version})" if version else "")


class HomeAssistant:
    """Your TVs through Home Assistant's REST API and a long-lived access token: the one
    the remote is on, its state every few seconds, and the buttons pressed, one at a
    time, on a thread of its own. homeassistant.txt:
        url = homeassistant.local:8123
        token = <long-lived access token>
        tv = media_player.living_room_tv      (optional: found by themselves; several, with commas between)
        remote = remote.living_room_tv        (optional: found by themselves; one for each tv, in order)
        style = samsung                       (optional: samsung, android, roku, apple, lg; one for each tv)
    """

    def __init__(self):
        self.cfg = {}
        self.url = self.token = ""
        self.tv = self.remote = self.style = ""     # the TV the remote is on
        self.listed, self.remotes, self.styles = [], [], []   # ...and what the file says
        self.tvs = []                # every TV found: [{"tv", "remote", "style", "name"}]
        self.pick = ""               # the one you picked last
        self.found = False
        self.loaded = None
        self.tvstate = {}
        self.watch = None            # (on or off, until when, when to ask again): turning it on or off, to see it
        self.working = False         # a button's being sent
        self.error = None
        self.jobs = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.running = False
        self.poll_now = False
        self.on_change = lambda: None
        self.on_note = lambda text, secs=3: None
        self.on_pick = lambda entity: None         # another TV picked (to remember it)

    def load(self, patterns, pick=""):
        self.cfg = read_config(patterns)
        self.pick = pick or self.pick
        url = ha_url(self.cfg.get("url", ""))
        key = (url, self.cfg.get("token", "").strip(), self.cfg.get("tv", "").strip(),
               self.cfg.get("remote", "").strip(), self.cfg.get("style", "").strip().lower())
        if key != self.loaded:                         # new settings: find the TVs again
            self.loaded = key
            self.url, self.token = key[:2]
            self.listed, self.remotes, self.styles = entity_list(key[2]), entity_list(key[3]), entity_list(key[4])
            self.tv = self.listed[0] if self.listed else ""
            self.remote = self.remotes[0] if self.remotes else ""
            self.style = self.styles[0] if self.styles else ""
            self.found, self.tvstate, self.error, self.tvs, self.watch = False, {}, None, [], None

    @property
    def configured(self):
        return bool(self.url and self.token)

    @property
    def where(self):
        return self.url.split("://", 1)[-1]

    # talking to Home Assistant
    def call(self, method, path, body=None, timeout=8):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = r.read()
        return json.loads(out) if out.strip() else None

    def why(self, e):
        if isinstance(e, urllib.error.HTTPError):
            if e.code == 401:
                return "Home Assistant didn't accept the token"
            try:
                body = e.read().decode("utf-8", "replace")
            except OSError:
                body = ""
            try:
                msg = json.loads(body).get("message")
            except (ValueError, AttributeError):
                msg = body.strip()[:80]
            return msg or f"Home Assistant said {e.code}"
        if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, OSError)):
            return f"Can't reach Home Assistant at {self.where}"
        return str(e) or "Something went wrong"

    def service(self, domain, name, **data):
        return self.call("POST", f"/api/services/{domain}/{name}", data)

    # finding the TVs (and each one's remote and kind) when the file doesn't say
    def discover(self):
        states = self.call("GET", "/api/states", timeout=15) or []
        ids = {st.get("entity_id"): st for st in states if isinstance(st, dict) and st.get("entity_id")}
        tvs = list(self.listed) or self.find_tvs(ids)
        if not tvs:
            raise ValueError("No TV in Home Assistant: put  tv = media_player.…  in the file")
        taken, found = set(self.remotes), []
        for k, tv in enumerate(tvs):                   # (the file's remotes and kinds go with its TVs, in order)
            remote = self.remotes[k] if k < len(self.remotes) else self.find_remote(tv, ids, taken, first=k == 0)
            taken.add(remote)
            style = self.styles[k] if k < len(self.styles) else self.find_style(tv, remote, ids)
            name = str((ids.get(tv) or {}).get("attributes", {}).get("friendly_name") or tv)
            found.append({"tv": tv, "remote": remote, "style": style, "name": name})
        self.tvs = found
        self.use(next((t for t in found if t["tv"] == self.pick), found[0]))
        self.found = True

    @staticmethod
    def find_tvs(ids):
        """Media players that are TVs: the ones Home Assistant says are, and players named like a TV with a remote
        of their own (a Roku stick, say); or, if none says it's a TV, the ones named like one."""
        players = [st for k, st in ids.items() if k.startswith("media_player.")]
        tvs = [st for st in players if st.get("attributes", {}).get("device_class") == "tv"]
        if not tvs:
            return [st["entity_id"] for st in players if words(st) & TV_WORDS]
        more = [st for st in players if st not in tvs and words(st) & TV_WORDS
                and "remote." + st["entity_id"].split(".", 1)[1] in ids]
        return [st["entity_id"] for st in tvs + more]

    @staticmethod
    def find_remote(tv, ids, taken, first=False):
        """A TV's remote: the one with its name, or one named like it (a remote only goes with one TV)."""
        same = "remote." + tv.split(".", 1)[1]
        if same in ids:
            return same
        remotes = [k for k in ids if k.startswith("remote.") and k not in taken]
        mine = words(ids.get(tv, {})) - {"media", "player", "tv", ""}
        near = [k for k in remotes if words(ids[k]) & mine]
        if near:
            return near[0]
        everyone = [k for k in ids if k.startswith("remote.")]
        return everyone[0] if first and len(everyone) == 1 and everyone[0] not in taken else ""

    @staticmethod
    def find_style(tv, remote, ids):
        seen = words(ids.get(tv, {})) | (words(ids[remote]) if remote in ids else set())
        return next((style for keys, style in TV_STYLE_WORDS if seen & keys), "samsung")

    def use(self, t):
        self.tv, self.remote, self.style = t["tv"], t["remote"], t["style"]

    def tv_names(self):
        """[(entity, name)] for each TV found, two with one name told apart by their entity."""
        names = [t["name"] for t in self.tvs]
        return [(t["tv"], t["name"] if names.count(t["name"]) == 1 else f"{t['name']} ({t['tv']})") for t in self.tvs]

    def choose(self, entity):
        """The remote on another TV (from the More menu). True if it's changed."""
        t = next((t for t in self.tvs if t["tv"] == entity), None)
        if t is None or entity == self.tv:
            return False
        with self.lock:
            self.jobs.clear()                          # (buttons meant for the other TV)
        self.pick = entity
        self.use(t)
        self.tvstate, self.error, self.watch = {"name": t["name"]}, None, None
        self.poll_now = True
        self.wake.set()
        self.on_pick(entity)
        self.on_change()
        return True

    def refresh(self):
        try:
            if not self.found:
                self.discover()
            tv = self.tv
            st = self.call("GET", f"/api/states/{tv}")
            if tv != self.tv:                          # (another TV picked meanwhile: its turn next)
                return
            a = st.get("attributes", {})
            self.tvstate = {"state": st.get("state", ""), "name": a.get("friendly_name") or self.tv,
                            "volume": a.get("volume_level"), "muted": bool(a.get("is_volume_muted")),
                            "source": a.get("source"), "sources": list(a.get("source_list") or []),
                            "title": a.get("media_title"), "app": a.get("app_name")}
            self.error = None
            self.check_watch()
        except urllib.error.HTTPError as e:
            if e.code == 404 and self.found and not self.listed:
                # the TV it found has gone (renamed in Home Assistant): look again
                self.found = False
                self.error = "Looking for your TV again"
            else:
                self.error = (f"Home Assistant has no {self.tv}" if e.code == 404 and self.found
                              else self.why(e))
        except Exception as e:
            self.error = self.why(e)
        if self.watch and time.monotonic() > self.watch[1]:
            self.check_watch()                         # (it's said nothing since: that it didn't happen)
        self.on_change()

    def check_watch(self):
        """Turning the TV on or off: say so once Home Assistant sees it happen, or that it didn't."""
        if not self.watch:
            return
        want, until, again = self.watch
        now = time.monotonic()
        if tv_power(self.tvstate.get("state")) == want:
            self.watch = None
            self.on_note(f"Your TV is {want}")
        elif now > until:
            self.watch = None
            self.on_note(f"Your TV didn't turn {want}", 5)
        elif want == "on" and self.style in WAKE_AGAIN and now >= again:
            self.watch = (want, until, now + HA_WAKE_AGAIN)
            try:                                       # (still off: wake it again)
                self.service("media_player", "turn_on", entity_id=self.tv)
            except Exception:
                pass

    # the buttons
    def send(self, *job):
        with self.lock:
            if len(self.jobs) < 8:                    # held buttons don't pile up
                self.jobs.append(job)
        self.wake.set()

    def busy(self):
        """A button still on its way to the TV (a held one waits for it: a slow TV doesn't fall behind)."""
        return self.working or bool(self.jobs)

    def run_job(self, job):
        what = job[0]
        tv = {"entity_id": self.tv}
        if what == "key":
            self.press_key(job[1])
        elif what == "channel":
            number = job[1]
            try:                                       # Samsung, LG and Android TV take a number
                cid = int(number) if self.style == "android" else number
                self.service("media_player", "play_media", media_content_type="channel",
                             media_content_id=cid, **tv)
            except (urllib.error.HTTPError, ValueError):
                for ch in number:                      # otherwise press the digits, then enter
                    self.press_key("dash" if ch in "-." else ch)
                    time.sleep(0.15)
                self.press_key("enter")
            self.on_note(f"Channel {number}")
        elif what == "volume":
            self.service("media_player", "volume_up" if job[1] > 0 else "volume_down", **tv)
        elif what == "mute":                        # (muted or not, as you picked)
            muted = job[1] if len(job) > 1 else not self.tvstate.get("muted")
            self.service("media_player", "volume_mute", is_volume_muted=bool(muted), **tv)
        elif what == "play":
            self.service("media_player", "media_play_pause", **tv)
        elif what == "power":                       # on or off, as you picked: never the other way
            self.refresh()                             # (how it is now, not a few seconds ago)
            now = tv_power(self.tvstate.get("state")) if not self.error else None
            want = job[1] if len(job) > 1 else ("off" if now == "on" else "on")
            if now == want:                            # (a TV that's on can take "on" as its power button)
                self.on_note(f"Your TV is already {want}")
                return
            try:
                self.service("media_player", "turn_" + want, **tv)
            except urllib.error.HTTPError as e:
                if e.code in (400, 500):               # e.g. a Samsung or an LG with no way set up to wake it
                    raise ValueError(f"Home Assistant can't turn this TV {want}")
                raise
            self.watch = (want, time.monotonic() + HA_WATCH, time.monotonic() + HA_WAKE_AGAIN)
            self.on_note(f"Turning your TV {want}…", 10)
        elif what == "source":
            self.service("media_player", "select_source", source=job[1], **tv)

    def press_key(self, name):
        tv = {"entity_id": self.tv}
        keys = TV_KEYS.get(self.style) or TV_KEYS["samsung"]
        if name not in keys:
            raise ValueError("This TV has no such button in Home Assistant")
        if self.style == "lg":
            self.service("webostv", "button", button=keys[name], **tv)
        elif self.remote:
            self.service("remote", "send_command", entity_id=self.remote, command=keys[name])
        else:
            raise ValueError("No remote for the buttons: add  remote = remote.…  to the file")

    # running while the TV Remote page is on screen
    def start(self):
        if self.running or not self.configured:
            return
        self.running = True
        threading.Thread(target=self.loop, daemon=True, name="home-assistant").start()

    def stop(self):
        self.running = False
        with self.lock:
            self.jobs.clear()
        self.wake.set()

    def poll_every(self):
        return 1.0 if self.watch else HA_POLL      # (every second while it turns on or off)

    def loop(self):
        next_poll = 0.0
        while self.running:
            with self.lock:
                job = self.jobs.pop(0) if self.jobs else None
            if job:
                self.working = True
                try:
                    if not self.found:
                        self.discover()
                    self.run_job(job)
                except Exception as e:
                    self.on_note(self.why(e) if not isinstance(e, ValueError) else str(e))
                finally:
                    self.working = False
                next_poll = min(next_poll, time.monotonic() + 0.5)
                continue
            if self.poll_now or time.monotonic() >= next_poll:
                self.poll_now = False
                self.refresh()
                next_poll = time.monotonic() + self.poll_every()
            self.wake.wait(0.25)
            self.wake.clear()


class HomeLights(HomeAssistant):
    """Your lights through Home Assistant (with the same url and token as the TV Remote): each one switched on and
    off and dimmed, your smart plugs switched, your scenes set, and all the lights off at once. homeassistant.txt
    may name the ones to show:
        lights = light.kitchen, light.lamp, switch.fan_plug     (optional: found by themselves)
    """

    def __init__(self):
        super().__init__()
        self.named = []              # the ones the file names, in its order
        self.rows = []               # [{"entity", "name", "kind": light|plug|scene, "on", "pct", "dims", "gone"}]
        self.held = {}               # entity -> {"until", "on", "pct"}: as set here, while the change is on its way
        self.last_pct = {}           # entity -> how bright it was when last on (what it comes back on at)
        self.thread = None

    def load(self, patterns, pick=""):
        self.cfg = read_config(patterns)
        key = (ha_url(self.cfg.get("url", "")), self.cfg.get("token", "").strip(), self.cfg.get("lights", "").strip())
        if key != self.loaded:                         # new settings: find the lights again
            self.loaded = key
            self.url, self.token = key[:2]
            self.named = entity_list(key[2])
            self.found, self.rows, self.error, self.held = False, [], None, {}

    @staticmethod
    def poll_every():
        return HA_LIGHTS_POLL

    def discover(self):
        self.refresh()

    @staticmethod
    def row_of(st):
        eid, a = st.get("entity_id", ""), st.get("attributes") or {}
        kind = {"light": "light", "switch": "plug", "scene": "scene"}.get(eid.split(".", 1)[0], "plug")
        modes = set(a.get("supported_color_modes") or [])
        dims = kind == "light" and (bool(modes - {"onoff"}) or "brightness" in a)
        on = st.get("state") == "on"
        try:
            pct = round(int(a.get("brightness") or 0) * 100 / 255) if on else 0
        except (TypeError, ValueError):
            pct = 0
        return {"entity": eid, "name": str(a.get("friendly_name") or eid), "kind": kind, "on": on,
                "pct": max(pct, 1) if on and dims else pct, "dims": dims, "gone": st.get("state") == "unavailable"}

    def refresh(self):
        try:
            states = self.call("GET", "/api/states", timeout=15) or []
            ids = {st.get("entity_id"): st for st in states if isinstance(st, dict) and st.get("entity_id")}
            if self.named:
                rows = [self.row_of(ids.get(e) or {"entity_id": e, "state": "unavailable"}) for e in self.named]
            else:
                rows = sorted((self.row_of(st) for e, st in ids.items()
                               if e.startswith("light.") or e.startswith("scene.")
                               or (e.startswith("switch.") and st.get("attributes", {}).get("device_class") == "outlet")),
                              key=lambda r: ({"light": 0, "plug": 1, "scene": 2}[r["kind"]], r["name"].lower()))
            now = time.monotonic()
            for k, r in enumerate(rows):               # (a change on its way: as it was set here)
                h = self.held.get(r["entity"])
                if h and h["until"] > now:
                    rows[k] = dict(r, on=h["on"], pct=h["pct"])
            self.last_pct.update({r["entity"]: r["pct"] for r in rows if r["on"] and r["dims"]})
            self.rows, self.found, self.error = rows, True, None
        except Exception as e:
            self.error = self.why(e)
        self.on_change()

    def lights(self):
        return [r for r in self.rows if r["kind"] != "scene"]

    def scenes(self):
        return [r for r in self.rows if r["kind"] == "scene"]

    # what you do, shown at once and sent after
    def send(self, *job):
        with self.lock:
            if job[0] == "dim":                        # (a held arrow: only where it ends up)
                self.jobs = [j for j in self.jobs if not (j[0] == "dim" and j[1] == job[1])]
            if len(self.jobs) < 16:
                self.jobs.append(job)
        self.wake.set()

    def hold(self, row):
        self.held[row["entity"]] = {"until": time.monotonic() + 3, "on": row["on"], "pct": row["pct"]}

    def toggle(self, row):
        """On or off (a scene: set)."""
        if row["kind"] == "scene":
            self.send("scene", row["entity"])
            self.on_note(f"{row['name']}")
            return
        row["on"] = not row["on"]
        if row["dims"]:
            row["pct"] = self.last_pct.get(row["entity"], 100) if row["on"] else 0
        self.hold(row)
        self.send("on" if row["on"] else "off", row["entity"], row["kind"])

    def dim(self, row, step):
        """Brighter or dimmer (one that doesn't dim: on or off)."""
        if row["kind"] == "scene":
            return
        if not row["dims"]:
            if row["on"] != (step > 0):
                self.toggle(row)
            return
        pct = max(0, min(100, (row["pct"] if row["on"] else 0) + step))
        if pct == (row["pct"] if row["on"] else 0):
            return
        row["on"], row["pct"] = pct > 0, pct
        self.hold(row)
        self.send("dim", row["entity"], pct)

    def all_off(self):
        on = [r for r in self.lights() if r["on"] and r["kind"] == "light"]
        for r in on:
            r["on"], r["pct"] = False, 0
            self.hold(r)
        if on:
            self.send("alloff", [r["entity"] for r in on])
        return len(on)

    # its thread: what's been pressed is sent even after you leave the page
    def start(self):
        if not self.configured:
            return
        with self.lock:
            self.running = True
            if self.thread is None:
                self.thread = threading.Thread(target=self.loop, daemon=True, name="home-assistant-lights")
                self.thread.start()

    def stop(self):
        self.running = False
        self.wake.set()

    def loop(self):
        next_poll = 0.0
        while True:
            with self.lock:
                job = self.jobs.pop(0) if self.jobs else None
                if job is None and not self.running:
                    self.thread = None
                    return
            if job:
                try:
                    self.run_job(job)
                except Exception as e:
                    self.on_note(self.why(e))
                next_poll = min(next_poll, time.monotonic() + 0.6)
                continue
            if self.poll_now or time.monotonic() >= next_poll:
                self.poll_now = False
                self.refresh()
                next_poll = time.monotonic() + self.poll_every()
            self.wake.wait(0.25)
            self.wake.clear()

    def run_job(self, job):
        what = job[0]
        if what == "scene":
            self.service("scene", "turn_on", entity_id=job[1])
        elif what in ("on", "off"):
            domain = "light" if job[2] == "light" else job[1].split(".", 1)[0]
            self.service(domain, "turn_on" if what == "on" else "turn_off", entity_id=job[1])
        elif what == "dim":
            if job[2] > 0:
                self.service("light", "turn_on", entity_id=job[1], brightness_pct=job[2])
            else:
                self.service("light", "turn_off", entity_id=job[1])
        elif what == "alloff":
            self.service("light", "turn_off", entity_id=job[1])
