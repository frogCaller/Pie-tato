"""The web page's Settings: everything the Pi's Settings app has, and the apps' own settings (Weather's, Home
Assistant's, the Bot's, the games'...), to see and change from a phone or a computer. Passwords and tokens never go
to the page: it's told whether there is one, and may put in another."""
import os
import re
import threading
import time

from ..config import (ACCENTS, SCREEN_MODES, WALLPAPERS, clean_name, edit_config, home_dir, read_config,
                      settings_glob)
from ..homeassistant import ha_typed_url, ha_url, save_ha
from ..pihole import dns_guess
from ..screen import boot_resolution
from ..util import IMAGE_EXTS
from ..voice import BOT_VOICES, VOICE_MB, voices_here
from ..listen import WAKE_MOST, mics
from ..bot import FRIEND_CHATTER
from ..crypto import CRYPTO_LINE, CRYPTO_MOST
from ..stocks import STOCKS_LINE, STOCKS_MOST, SYMBOL
from ..net import cam_address
from ..weather import geocode, place_text
from ..games import system
from .weather import WX_UNITS
from .games import DS_SCREENS, DS_TOUCH, GAME_PICTURES

ENTITY = re.compile(r"[a-z_]+\.[a-z0-9_]+")          # a Home Assistant entity: light.kitchen
COIN = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")         # a coin, as CoinGecko knows it: bitcoin, shiba-inu
PLACE_KEYS = ("lat", "lon", "name")                    # what a place from the search must have (and may: admin,
PLACE_MORE = ("admin", "country")                      # country)
WIFI_SAID = 30                                         # seconds: how connecting to a network went, said that long


def hex_of(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def words_list(text, pattern, upper=False):
    """A list with commas between: each one tidied, checked, once. (the list, or None: one isn't right.)"""
    out = []
    for w in re.split(r"[,;\n]+", text or ""):         # (not spaces: "Shiba Inu" is a name, not two coins)
        w = w.strip().upper() if upper else w.strip().lower()
        if not w:
            continue
        if not pattern.fullmatch(w):
            return None
        if w not in out:
            out.append(w)
    return out


class WebSettingsScreen:
    """The web page's Settings (web_settings: what they are; web_settings_do: one changed, on media mode's own
    thread; web_find_place: towns for Weather's location, asked of the internet on the web page's)."""

    # -- what they are --------------------------------------------------------------------------------------------
    def web_settings(self):
        """(The web page's thread: it only reads, and tries again if the main loop changed something under it.)"""
        for _ in range(3):
            try:
                return self.web_settings_now()
            except (RuntimeError, IndexError, KeyError, AttributeError, TypeError):
                time.sleep(0.02)
        return self.web_settings_now()

    def web_settings_now(self):
        sections = []
        root = {k: (label, choices) for k, label, choices in self.settings_root_rows()}

        def sec(sid, title, rows, about=""):
            rows = [r for r in rows if r]
            if rows:
                sections.append({"id": sid, "title": title, "about": about, "rows": rows})

        def choice(key, label=None, choices=None, value=None, **more):
            label = label or root[key][0]
            choices = list(choices if choices is not None else root[key][1])
            value = self.setting(key) if value is None else value
            return dict(key=key, label=label, kind="choice", value=value, choices=choices, **more)

        def said(pair):
            """A job's (ok, words): the words, and their tone."""
            if not pair:
                return {}
            ok, words = pair
            return {"status": words, "tone": "busy" if ok == "busy" else "ok" if ok else "bad"}

        # the screen
        rows = [choice("wallpaper", choices=WALLPAPERS, picture=os.path.basename(self.setting("picture") or "")),
                choice("home_style"),
                choice("accent", colours={a: hex_of(rgb) for a, rgb in ACCENTS}),
                choice("clock"), choice("app_full")]
        if "turn" in root:
            rows.append(choice("turn"))
        info = self.res_info() if "resolution" in root else None
        if info:
            rows.append(choice("resolution", "Resolution", ["Auto"] + list(info[1]), value=boot_resolution() or "Auto",
                               names={"Auto": f"Auto ({info[0]})"},
                               confirm="The Pi restarts at this size, then asks on its screen whether to keep it. "
                                       "If nobody says so, it goes back."))
        sec("screen", "Screen", rows)
        sound = choice("sound", "Sound", root["sound"][1])
        if sound["value"] in (None, "", "Auto"):
            sound["value"] = "Auto"
            if self.sound_value() != "Auto":
                sound["note"] = self.sound_value()     # (Auto: HDMI, say)
        sec("sound", "Sound and video", [sound, choice("screen", "Video size", SCREEN_MODES)])
        sec("start", "Starting up", [choice("start"), choice("start_song")])

        # WiFi
        w, went = self.wifi, self.wifi.get("said")
        status, tone = (w["status"] or "").replace(". X looks again", ""), "busy" if w["busy"] else ""
        if not w["busy"] and went and time.monotonic() - went[2] < WIFI_SAID:   # how connecting went, a while
            status, tone = went[1], "ok" if went[0] else "bad"
        sec("wifi", "WiFi", [{"key": "wifi", "label": "WiFi", "kind": "wifi", "radio": w["radio"],
                              "here": self.current_ssid(), "busy": w["busy"], "status": status, "tone": tone,
                              "nets": [{"ssid": n["ssid"], "signal": n["signal"], "secure": n["secure"],
                                        "active": n["active"], "saved": n["ssid"] in w["saved"]}
                                       for n in w["nets"]]}])

        # Weather
        loc, finding = self.setting("location"), self.loc_status or ""
        sec("weather", "Weather", [
            {"key": "location", "label": "Location", "kind": "place", "value": place_text(loc) if loc else "",
             "status": finding, "tone": "busy" if finding.endswith("…") else "bad" if finding else ""},
            choice("units", "Temperature", WX_UNITS, value=self.setting("units") if self.setting("units") in WX_UNITS
                   else WX_UNITS[0])])

        # Home: your Home Assistant
        cfg = read_config(self.ha_files())
        url, token = ha_url(cfg.get("url", "")), bool(cfg.get("token", "").strip())
        rows = [{"key": "ha_url", "label": "Address", "kind": "text", "value": url.split("://", 1)[-1]
                 if url.startswith("http://") else url, "placeholder": "homeassistant.local:8123", "max": 120},
                {"key": "ha_token", "label": "Long-lived token", "kind": "secret", "set": token, "max": 600,
                 "note": "In Home Assistant: your profile, Security, Long-lived access tokens, Create token. "
                         "Copy it, and paste it here."},
                dict({"key": "ha_check", "label": "Connection", "kind": "action", "button": "Check",
                      "disabled": not (url and token)}, **said(self.ha_said)),
                {"key": "ha_lights", "label": "Lights to show", "kind": "text", "value": cfg.get("lights", ""),
                 "placeholder": "All of them, or light.kitchen, switch.fan_plug", "max": 600},
                {"key": "ha_tv", "label": "TVs", "kind": "text", "value": cfg.get("tv", ""),
                 "placeholder": "Found by themselves, or media_player.living_room_tv", "max": 600}]
        if url or token:
            rows.append({"key": "ha_forget", "label": "", "kind": "action", "button": "Forget Home Assistant",
                         "tone": "bad", "confirm": "Its address and token are taken off the Pi."})
        sec("ha", "Home", rows, "Your Home Assistant: the TV Remote and Lights work your TVs and lights through it.")

        # Pi-hole
        ph = self.pihole
        if ph.configured:
            rows = [{"key": "ph_where", "label": "Address", "kind": "info", "value": ph.url.split("://", 1)[-1]},
                    dict({"key": "ph_state", "label": "Now", "kind": "info", "value": ""},
                         **({"status": ph.error, "tone": "bad"} if ph.error else
                            {"status": "Answering", "tone": "ok"} if ph.found else {})),
                    {"key": "ph_forget", "label": "", "kind": "action", "button": "Forget your Pi-hole", "tone": "bad",
                     "confirm": "Its address and password are taken off the Pi."}]
        else:
            rows = [dict({"key": "ph_add", "label": "Add your Pi-hole", "kind": "form", "button": "Add",
                          "fields": [{"name": "url", "label": "Address", "placeholder": dns_guess() or "192.168.1.2"},
                                     {"name": "password", "label": "Password", "secret": True,
                                      "placeholder": "Its password, or an app password (none if it has none)"}]},
                         **said(getattr(self, "ph_said", None)))]
        sec("pihole", "Pi-hole", rows, "Its dashboard, on the Home tab.")

        # Plex and Jellyfin
        px, pi = self.plex, self.tab_index("plex")
        pin = px.pin or {}
        state = "in" if px.signed_in else "code" if pin.get("code") else \
            "busy" if self.status.get(pi) in ("code", "finding") else "out"
        sec("plex", "Plex", [{"key": "plex", "label": "Plex", "kind": "signin", "state": state,
                              "who": px.server_name if px.ready else "", "code": pin.get("code", ""),
                              "where": "plex.tv/link", "problem": {"offline": "Can't reach plex.tv",
                                                                    "noserver": "No Plex server found"}.get(
                                  self.status.get(pi), "")}])
        jf, ji = self.jellyfin, self.tab_index("jellyfin")
        man = read_config([settings_glob("jellyfin.txt")])
        q = jf.quick or {}
        state = "in" if jf.ready else "code" if q.get("code") else \
            "busy" if self.status.get(ji) in ("finding", "signing") else "out"
        sec("jellyfin", "Jellyfin", [
            {"key": "jellyfin", "label": "Jellyfin", "kind": "signin", "state": state,
             "who": jf.server_name if jf.ready else "", "code": q.get("code", ""),
             "where": "Jellyfin: your profile, Quick Connect",
             "problem": {"noserver": "No Jellyfin server found", "noquick": "Quick Connect is off on your server",
                         "badlogin": "Jellyfin didn't take that user and password",
                         "offline": "Can't reach Jellyfin"}.get(self.status.get(ji), "")},
            {"key": "jf_server", "label": "Server", "kind": "text", "value": man.get("server", ""),
             "placeholder": "Found by itself (or 192.168.1.10:8096)", "max": 120},
            {"key": "jf_user", "label": "User", "kind": "text", "value": man.get("user", ""),
             "placeholder": "Only to sign in without Quick Connect", "max": 80},
            {"key": "jf_password", "label": "Password", "kind": "secret", "set": bool(man.get("password")),
             "max": 200}])

        # the Bot
        fr = self.friend
        fr.load(self.friend_files())
        if fr.server and fr.models_at != fr.server and getattr(self, "web_models_for", None) != fr.server:
            self.web_models_for = fr.server            # (its models asked for once, as Settings > Bot does)
            fr.fetch_models()
        models = list(fr.models) if fr.server and fr.models_at == fr.server else []
        if fr.model and fr.model not in models:
            models = [fr.model] + models
        chatter = [(t, str(v)) for t, v in FRIEND_CHATTER]
        here = voices_here()
        ours = [i for i, _, _ in BOT_VOICES]
        voices = [("", "None")] + [(i, n + (f" ({note})" if note else "") + ("" if i in here else f", {VOICE_MB} MB"))
                                   for i, n, note in BOT_VOICES] + [(v, v) for v in sorted(here) if v not in ours]
        asking = fr.models_status or ""
        rows = [{"key": "f_server", "label": "Computer with Ollama", "kind": "text", "value": fr.server,
                 "placeholder": "192.168.1.20", "max": 120, "status": asking,
                 "tone": "busy" if asking.endswith("…") else "ok" if fr.models and fr.models_at == fr.server
                 else "bad" if asking and fr.server else ""},
                {"key": "f_model", "label": "Model", "kind": "choice", "value": fr.model, "choices": models, "list": True,
                 "empty": "Set the computer first" if not fr.server else "Asking for its models…"
                 if asking.endswith("…") else "No models found"},
                {"key": "f_name", "label": "What it calls you", "kind": "text", "value": fr.name,
                 "placeholder": "Your name (optional)", "max": 40},
                {"key": "f_chatter", "label": "Says something by itself", "kind": "choice",
                 "value": str(fr.chatter()), "choices": [v for _, v in chatter], "names": {v: t for t, v in chatter}}]
        if self.voice.supported():
            job = self.voice.job
            rows += [{"key": "f_voice", "label": "Voice", "kind": "choice", "value": (job or {}).get("id")
                      or self.bot_voice(), "choices": [i for i, _ in voices], "names": dict(voices),
                      "status": self.voice.status() or "",
                      "tone": "busy" if job else "bad" if self.voice.error else ""},
                     {"key": "f_speak", "label": "Says its replies out loud", "kind": "choice",
                      "value": "on" if self.bot_speaks() else "off", "choices": ["on", "off"],
                      "names": {"on": "Yes", "off": "No"}}]
        found = mics()
        usable = [c for c in found if not c["plays"]] if getattr(self, "case", None) else found
        if usable or self.bot_listens():
            note, lit = self.listen_note()
            e = self.ears
            tone = "busy" if e.job or (note or "").endswith("…") else "ok" if lit else \
                "bad" if e.got_error or (self.bot_listens() and (e.unknown or e.state == "error")) else ""
            rows += [{"key": "f_listen", "label": "Listens for you", "kind": "choice",
                      "value": "on" if self.bot_listens() else "off", "choices": ["off", "on"],
                      "names": {"off": "Off", "on": "On"}, "status": note or "", "tone": tone},
                     {"key": "f_wake", "label": "Wake phrase", "kind": "text", "value": self.bot_wake(),
                      "placeholder": "hey potato", "max": WAKE_MOST}]
            if len(found) > 1 or self.bot_mic_set():
                rows.append({"key": "f_mic", "label": "Microphone", "kind": "choice", "value": self.bot_mic_set(),
                             "list": True,
                             "choices": [""] + [c["id"] for c in found],
                             "names": dict([("", "Auto")] + [(c["id"], c["name"]) for c in found])})
        rows += [{"key": "bot_mode", "label": "Its page", "kind": "choice", "value": self.bot_mode(),
                  "choices": ["chat", "work"], "names": {"chat": "Chat", "work": "At work (your coding agent)"}},
                 choice("coder_sound", "Sounds at work", ["On", "Off"],
                        value="Off" if self.setting("coder_sound") == "Off" else "On")]
        sec("bot", "Bot", rows, "It talks through Ollama on another computer on your network.")

        # the games
        gi = self.tab_index("games")
        systems = []
        for it in self.items.get(gi) or []:
            key = it.get("system")
            if key and key not in systems:
                systems.append(key)
        rows = [choice(f"game_picture_{k}", f"{system(k)[2]}: picture", GAME_PICTURES, value=self.game_picture(k))
                for k in systems]
        if "nds" in systems:
            rows += [choice("ds_screens", "DS: the two screens", [k for k, _ in DS_SCREENS],
                            value=self.setting("ds_screens") if self.setting("ds_screens") in dict(DS_SCREENS)
                            else DS_SCREENS[0][0], names=dict(DS_SCREENS)),
                     choice("ds_touch", "DS: touching the screen", DS_TOUCH,
                            value=self.setting("ds_touch") if self.setting("ds_touch") in DS_TOUCH else DS_TOUCH[0])]
        sec("games", "Games", rows, "Each console's games keep the picture you pick for them.")
        sec("sim", "Simulator", [choice("sim_full", "Full screen", ["Off", "On"],
                                        value="On" if self.setting("sim_full") == "On" else "Off")])

        # Finance
        coins = getattr(self, "crypto", None)
        sec("finance", "Finance", [
            {"key": "fin_stocks", "label": "Stocks", "kind": "text", "value": ", ".join(self.stocks.symbols()),
             "placeholder": "AAPL, AMZN, TSLA", "max": 400, "note": "Their tickers, as on finance.yahoo.com"},
            {"key": "fin_coins", "label": "Coins", "kind": "text", "value": ", ".join(coins.ids() if coins else []),
             "placeholder": "bitcoin, ethereum", "max": 400, "note": "As coingecko.com names them, in its addresses"}])

        # this web page
        web = read_config([settings_glob("webui.txt")])
        sec("web", "This web page", [
            {"key": "web_password", "label": "Password", "kind": "secret", "set": bool(web.get("password")),
             "max": 120, "note": "Then your browser asks for it (any user name)."},
            {"key": "web_hosts", "label": "Other names you open it by", "kind": "text",
             "value": web.get("hosts", ""), "placeholder": "Like pi.example.com", "max": 200}])
        return {"sections": sections}

    # -- one changed (media mode's own thread) -------------------------------------------------------------------------
    def web_settings_do(self, cmd):
        key = str(cmd.get("key") or "")
        value = cmd.get("value")
        if key in ("home_style", "clock", "app_full", "turn", "start", "start_song", "wallpaper", "accent", "sound",
                   "screen", "units", "sim_full", "coder_sound", "ds_screens", "ds_touch") \
                or key.startswith("game_picture_"):
            return self.web_pick(key, value)
        handler = getattr(self, "web_set_" + key, None)
        if not key.isidentifier() or handler is None:
            return {"error": "No such setting"}
        return handler(value, cmd)

    def web_choices(self, key):
        """What a setting may be, as web_settings says."""
        for sec in self.web_settings_now()["sections"]:
            for row in sec["rows"]:
                if row["key"] == key and row["kind"] == "choice":
                    return row["choices"]
        return None

    def web_pick(self, key, value):
        choices = self.web_choices(key)
        if choices is None or value not in choices:
            return {"error": "That isn't one of its choices"}
        if key == "wallpaper" and value == "Picture" and not self.setting("picture"):
            return {"error": "Pick a picture for it"}
        if key == "sim_full" and self.tab_type() == "sim":
            self.sim_set_full(value == "On")           # (the sim on the screen grows or shrinks)
        else:
            self.set_setting(key, value)
        if key == "units":
            self.weather_changed()
        return {"ok": True}

    def web_set_picture(self, value, cmd):
        """The background: one of your pictures (webui.py says where it is)."""
        pics = os.path.realpath(os.path.join(home_dir(), "Pictures"))
        path = os.path.realpath(value) if isinstance(value, str) and value.startswith("/") else ""
        if not (path.startswith(pics + os.sep) and os.path.splitext(path)[1].lower() in IMAGE_EXTS
                and os.path.isfile(path)):
            return {"error": "That isn't one of your pictures"}
        self.set_setting("picture", path)
        self.set_setting("wallpaper", "Picture")
        return {"ok": True}

    def web_set_resolution(self, value, cmd):
        info = self.res_info()
        if not info or value not in ["Auto"] + list(info[1]):
            return {"error": "The screen doesn't take that size"}
        size = None if value == "Auto" else value
        if size == boot_resolution():
            return {"ok": True}
        if not (self.active and self.fb):
            return {"error": "Open media mode first: the Pi asks on its screen whether to keep it"}
        self.res_apply(size)
        return {"ok": True, "said": "The Pi restarts at the new size"}

    def web_set_location(self, value, cmd):
        if value == "find":                            # from the internet address
            self.loc_status = "Finding you…"
            threading.Thread(target=self.locate_job, args=(None,), daemon=True).start()
            return {"ok": True}
        if not (isinstance(value, dict) and all(k in value for k in PLACE_KEYS)):
            return {"error": "Pick a town from the list"}
        try:
            place = {k: v for k, v in value.items() if k in PLACE_KEYS + PLACE_MORE}
            place["lat"], place["lon"] = float(place["lat"]), float(place["lon"])
        except (TypeError, ValueError):
            return {"error": "Pick a town from the list"}
        if not (-90 <= place["lat"] <= 90 and -180 <= place["lon"] <= 180):
            return {"error": "Pick a town from the list"}
        place = {k: clean_name(v, 80) if isinstance(v, str) else v for k, v in place.items()}
        self.set_setting("location", place)
        self.loc_status = None
        self.weather_changed()
        return {"ok": True, "said": f"Location: {place_text(place)}"}

    # Home Assistant
    def web_ha_saved(self, updates, said="Saved"):
        try:
            save_ha(updates)
        except OSError as ex:
            return {"error": f"Couldn't save it ({ex.strerror or ex})"}
        self.hass.load(self.ha_files())
        self.lights.load(self.ha_files())
        if {"url", "token"} & set(updates):           # (a check said for another address or token: not now)
            self.ha_said = None
        if self.tab_type() in ("remote", "lights", "group", "settings") and self.view == "list":
            self.load_tab(self.tab)                    # (on the Pi's screen: as it is now)
        self.dirty = True
        return {"ok": True, "said": said}

    def web_set_ha_url(self, value, cmd):
        url = ha_typed_url(str(value or ""))           # (no port: Home Assistant's own, 8123)
        if not re.fullmatch(r"https?://[^/\s]+(/[^\s]*)?", url):
            return {"error": "That isn't an address. Try one like homeassistant.local:8123"}
        out = self.web_ha_saved({"url": url})
        if out.get("ok") and self.hass.token:
            self.ha_check_now()
        return out

    def web_set_ha_token(self, value, cmd):
        token = "".join(str(value or "").split())
        if token and len(token) < 20:
            return {"error": "That's too short for a long-lived token"}
        out = self.web_ha_saved({"token": token}, "Saved" if token else "Taken off")
        if out.get("ok") and token and self.hass.url:
            self.ha_check_now()
        return out

    def web_set_ha_check(self, value, cmd):
        self.ha_check_now()
        return {"ok": True}

    def web_set_ha_lights(self, value, cmd):
        return self.web_ha_entities("lights", value)

    def web_set_ha_tv(self, value, cmd):
        return self.web_ha_entities("tv", value)

    def web_ha_entities(self, name, value):
        ids = words_list(str(value or ""), ENTITY)
        if ids is None:
            return {"error": "Those aren't Home Assistant entities. Like light.kitchen, with commas between"}
        return self.web_ha_saved({name: ", ".join(ids)})

    def web_set_ha_forget(self, value, cmd):
        return self.web_ha_saved({"url": "", "token": ""}, "Forgot Home Assistant")

    # Pi-hole
    def web_set_ph_add(self, value, cmd):
        """Your Pi-hole: found at the address (on 8080, or else 80, with no port), signed in to, and kept. The
        asking's on a thread of its own: the page hears how it went."""
        from ..pihole import Busy, Denied, NotPihole, TwoFactor, pihole_url
        value = value if isinstance(value, dict) else {}
        url = pihole_url(str(value.get("url") or ""))
        password = str(value.get("password") or "")[:200]
        if not url:
            return {"error": "That isn't an address. Try one like 192.168.1.2:8080"}
        self.ph_said = ("busy", "Looking for it…")

        def job():
            try:
                there, version, needs = self.pihole.find(url)
                if needs and not password:
                    self.ph_said = (False, "It has a password: put it in too")
                    return
                version, sid = self.pihole.check(there, password)
            except Denied:
                self.ph_said = (False, "It didn't take that password")
                return
            except TwoFactor:
                self.ph_said = (False, "It wants a two-factor code too: use an app password")
                return
            except Busy:
                self.ph_said = (False, "Too many are signed in to it: try again in a while")
                return
            except NotPihole:
                self.ph_said = (False, "That doesn't answer as a Pi-hole")
                return
            except Exception:
                self.ph_said = (False, f"Can't reach {url.split('://', 1)[1]}")
                return
            self.ph_said = None
            self.soon(lambda: self.pihole_save(there, password, version, sid))
        threading.Thread(target=job, daemon=True, name="pihole-web").start()
        return {"ok": True}

    def web_set_ph_forget(self, value, cmd):
        if not self.pihole.configured:
            return {"ok": True}
        self.pihole_forget()
        return {"ok": True, "said": "Forgot your Pi-hole"}

    # Plex and Jellyfin
    def web_set_plex(self, value, cmd):
        if value == "signin":
            if self.plex.signed_in:
                return {"ok": True}
            if not (self.plex.pin or self.status.get(self.tab_index("plex")) in ("code", "finding")):
                self.plex_sign_in()
            return {"ok": True}
        if value == "signout":
            self.plex.sign_out()
            self.plex_stack = []
            self.items[self.tab_index("plex")] = []
            return {"ok": True, "said": "Signed out of Plex"}
        return {"error": "Bad request"}

    def web_set_jellyfin(self, value, cmd):
        ji = self.tab_index("jellyfin")
        if value == "signin":
            if self.jellyfin.ready:
                return {"ok": True}
            if not (self.jellyfin.quick or self.status.get(ji) in ("finding", "signing")):
                self.jf_sign_in()
            return {"ok": True}
        if value == "signout":
            self.jellyfin.sign_out()
            self.jf_stack = []
            self.items[ji] = []
            return {"ok": True, "said": "Signed out of Jellyfin"}
        return {"error": "Bad request"}

    def web_jellyfin_file(self, name, value):
        try:
            edit_config("jellyfin.txt", {name: value}, head="# Jellyfin: the server (when it isn't found by itself),"
                        " and a user and password (to sign in without Quick Connect). Keep it private.\n",
                        limit=200, private=True)
        except OSError as ex:
            return {"error": f"Couldn't save it ({ex.strerror or ex})"}
        return {"ok": True}

    def web_set_jf_server(self, value, cmd):
        text = str(value or "").strip()
        if text and not re.fullmatch(r"(https?://)?[A-Za-z0-9.-]+(:\d+)?/?", text):
            return {"error": "That isn't an address. Try one like 192.168.1.10:8096"}
        return self.web_jellyfin_file("server", text)

    def web_set_jf_user(self, value, cmd):
        return self.web_jellyfin_file("user", clean_name(value, 80))

    def web_set_jf_password(self, value, cmd):
        return self.web_jellyfin_file("password", str(value or "").strip()[:200])

    # the Bot
    def web_set_f_server(self, value, cmd):
        text = " ".join(str(value or "").split())[:120]
        if text and not cam_address(text):
            return {"error": "That isn't an address. Try 192.168.1.20"}
        if not self.friend_set(server=text):
            return {"error": "Couldn't save static/bot.txt"}
        if text:
            self.friend.fetch_models()
        return {"ok": True}

    def web_set_f_model(self, value, cmd):
        fr = self.friend
        if not isinstance(value, str) or value not in (fr.models if fr.models_at == fr.server else []):
            return {"error": "That model isn't on the computer with Ollama"}
        return {"ok": True} if self.friend_set(model=value) else {"error": "Couldn't save static/bot.txt"}

    def web_set_f_name(self, value, cmd):
        return {"ok": True} if self.friend_set(name=clean_name(value, 40)) else {"error": "Couldn't save static/bot.txt"}

    def web_set_f_chatter(self, value, cmd):
        if str(value) not in [str(v) for _, v in FRIEND_CHATTER]:
            return {"error": "That isn't one of its choices"}
        return {"ok": True} if self.friend_set(chatter=str(value)) else {"error": "Couldn't save static/bot.txt"}

    def web_set_f_voice(self, value, cmd):
        ok, what = self.voice_pick(clean_name(value, 80))
        return {"ok": True, "said": what} if ok else {"error": what}

    def web_set_f_speak(self, value, cmd):
        if value not in ("on", "off"):
            return {"error": "That isn't one of its choices"}
        if value == "on" and not self.bot_voice():
            return {"error": "Pick a voice first"}
        if not self.friend_set(speak=value):
            return {"error": "Couldn't save static/bot.txt"}
        if value == "off":
            self.voice.stop()
        return {"ok": True}

    def web_set_f_listen(self, value, cmd):
        if value not in ("on", "off"):
            return {"error": "That isn't one of its choices"}
        if (value == "on") != self.bot_listens():
            self.listen_toggle()
        return {"ok": True}

    def web_set_f_wake(self, value, cmd):
        self.listen_wake_typed(str(value or ""))
        return {"ok": True}

    def web_set_f_mic(self, value, cmd):
        if value not in [""] + [c["id"] for c in mics()]:
            return {"error": "That microphone isn't plugged in"}
        return {"ok": True} if self.friend_set(mic=value) else {"error": "Couldn't save static/bot.txt"}

    def web_set_bot_mode(self, value, cmd):
        if value not in ("chat", "work"):
            return {"error": "That isn't one of its choices"}
        self.set_setting("bot_mode", value)
        return {"ok": True}

    # Finance
    def web_set_fin_stocks(self, value, cmd):
        syms = words_list(str(value or ""), SYMBOL, upper=True)
        if syms is None:
            return {"error": "Those aren't tickers. Like AAPL, AMZN, with commas between"}
        if len(syms) > STOCKS_MOST or len(", ".join(syms)) > STOCKS_LINE:
            return {"error": f"That's more than the tab has room for ({STOCKS_MOST} at most)"}
        return {"ok": True} if self.fin_save(stocks=syms) else {"error": "Couldn't save static/finance.txt"}

    def web_set_fin_coins(self, value, cmd):
        ids = words_list(str(value or ""), COIN)
        if ids is None:
            return {"error": "Those aren't coins as CoinGecko names them. Like bitcoin, ethereum"}
        if len(ids) > CRYPTO_MOST or len(", ".join(ids)) > CRYPTO_LINE:
            return {"error": f"That's more than the tab has room for ({CRYPTO_MOST} at most)"}
        return {"ok": True} if self.fin_save(coins=ids) else {"error": "Couldn't save static/finance.txt"}

    # this web page
    def web_page_file(self, updates):
        try:
            edit_config("webui.txt", updates, head="# The web page: a password if you want it to ask for one, and "
                        "other names you open it by. Keep it private.\n", limit=200, private=True)
        except OSError as ex:
            return {"error": f"Couldn't save it ({ex.strerror or ex})"}
        return {"ok": True}

    def web_set_web_password(self, value, cmd):
        pw = str(value or "").strip()[:120]
        out = self.web_page_file({"password": pw})
        return dict(out, said="Your browser asks for it now" if pw else "No password now") if out.get("ok") else out

    def web_set_web_hosts(self, value, cmd):
        hosts = [h for h in re.split(r"[,\s]+", str(value or "")) if h]
        if any(not re.fullmatch(r"[A-Za-z0-9.-]{1,120}", h) for h in hosts):
            return {"error": "Names only, like pi.example.com, with commas between"}
        return self.web_page_file({"hosts": ", ".join(hosts)})

    # WiFi
    def web_set_wifi(self, value, cmd):
        w = self.wifi
        value = value if isinstance(value, dict) else {}
        do = value.get("do")
        if w["busy"] and do != "look":
            return {"error": "One thing at a time. Try again in a moment"}
        if do == "look":
            self.wifi_rescan()
            return {"ok": True}
        if do == "radio":                              # on or off, as Settings > WiFi's first row
            on = bool(value.get("on"))
            if on != w["radio"]:
                w["busy"], w["status"] = True, "Turning WiFi on…" if on else "Turning WiFi off…"
                threading.Thread(target=self.wifi_job, args=("radio", on), daemon=True).start()
            return {"ok": True}
        ssid = clean_name(value.get("ssid"), 64)
        if not ssid:
            return {"error": "Which network?"}
        if do == "connect":
            pw = value.get("password")
            pw = str(pw)[:128] if pw is not None else None
            if pw is not None and pw and len(pw) < 8:
                return {"error": "A WiFi password is 8 characters or more"}
            self.wifi_connect(ssid, pw or (None if not value.get("hidden") else ""), hidden=bool(value.get("hidden")))
            return {"ok": True}
        if do == "forget":
            if ssid not in w["saved"]:
                return {"error": "That network isn't saved"}
            w["busy"], w["status"] = True, f"Forgetting {ssid}…"
            threading.Thread(target=self.wifi_job, args=("forget", ssid), daemon=True).start()
            return {"ok": True}
        return {"error": "Bad request"}

    # -- towns, for Weather's location (the web page's thread: it asks the internet) ------------------------------------
    @staticmethod
    def web_find_place(text):
        text = " ".join(str(text or "").split())[:80]
        if not text:
            return {"error": "Type a town first"}
        try:
            found = geocode(text)
        except Exception:
            return {"error": "Can't reach the internet"}
        return {"places": [dict(r, label=place_text(r) + (f", {r['country']}" if r.get("country") else ""))
                           for r in found[:12]]}
