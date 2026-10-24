"""Media mode: class Media, with each app's part of it (pitato/screens/) mixed in."""
import fcntl
import json
import os
import random
import shutil
import subprocess
import threading
import time

from .theme import set_accent, TEXT
from .config import home_dir, HOME_STYLE_WAS, SCREEN_MODES, SETTINGS_DEFAULT, STATE_FILE, web_private
from .util import classify, clock, FILE_KINDS, find_files, IMAGE_EXTS, item, looks_like_text, title_of
from .system import system_info, system_stopping
from .bluetooth import Bluetooth
from .screen import Framebuffer, slow_pi
from .library import (
    BOOT_SONG_WAIT, fit_box, LIBRARY, LISTEN_KINDS, MEDIA_VT, PLAYING, read_streams, SCREEN_KINDS, SCREEN_SAY,
    SLIDESHOW_SECS, VOLUME_STEP)
from .weather import Weather
from .documents import doc_text
from .cameras import CAM_SHOT_SHOW, Camera
from .nearby import PieInk
from .voice import Voice
from .bot import Friend, FRIEND_PAGES
from .coder import AgentPrompts, Coder, CODER_FPS
from .crypto import Crypto
from .stocks import Stocks
from .homeassistant import HomeAssistant, HomeLights
from .plex import Plex, PLEX_TIMELINE_SECS
from .jellyfin import Jellyfin
from .sims import SIM_FPS, SIM_FPS_BIG
from .snake import SnakeBrain
from .shrink import Shrinker
from .computers import Computers
from .inputs import gpi_case_set_up, HALT_WAIT, KeyReader, show_shutdown_lines
from .screens.sims import SIMS
from .screens.draw import DrawScreen
from .screens.home import HomeScreen
from .screens.keyboard import KeyboardScreen
from .screens.player import PlayerScreen
from .screens.plex import PlexScreen
from .screens.jellyfin import JellyfinScreen
from .screens.photos import PhotoScreen
from .screens.reading import ReadingScreen
from .screens.channels import ChannelScreen
from .screens.radio import RadioScreen
from .screens.finance import FinanceScreen
from .screens.remote import RemoteScreen
from .screens.lights import LightsScreen
from .screens.camera import CameraScreen
from .screens.bot import BotScreen
from .screens.coder import CoderScreen
from .screens.sims import SimScreen
from .screens.snake import SnakeScreen
from .screens.games import GameScreen
from .screens.settings import SettingsScreen
from .screens.bluetooth import BluetoothScreen
from .screens.controller import ControllerScreen
from .screens.weather import WeatherScreen
from .screens.web import WebScreen
from .screens.computers import ComputersScreen, NET

_SAVING = threading.Lock()     # (state.json written one at a time: the shrinker's and radio's threads save too)


class Media(DrawScreen, HomeScreen, KeyboardScreen, PlayerScreen, PlexScreen, JellyfinScreen,
            PhotoScreen, ReadingScreen, ChannelScreen, RadioScreen, FinanceScreen,
            RemoteScreen, LightsScreen, CameraScreen, BotScreen, CoderScreen, SimScreen,
            SnakeScreen, GameScreen, SettingsScreen, BluetoothScreen, ControllerScreen, WeatherScreen, WebScreen,
            ComputersScreen):
    """Media mode: what the screen shows and what the buttons do there. Its state is all here; each
    app's buttons and drawing come from its part (pitato/screens/)."""

    REPEAT_VIEWS = ("list", "photo", "pdf", "text", "home", "keys")
    STATUS_VIEWS = ("list", "now", "help", "text", "home")

    def __init__(self):
        self.active = False
        self.tab = 0
        self.tab_off = 0            # how far the tab strip is scrolled
        self.items = {}             # tab index -> list of items
        self.status = {}            # tab index -> "loading" / "error"
        self.sels, self.tops = {}, {}
        self.view = "list"          # list, help, now, photo, pdf, text, wait
        self.help_from = "list"
        self.v = {}                 # state of the open photo / pdf / text viewer
        self.proc = None
        self.kind = None            # playing: video, audio, live, radio, plex (Plex or Jellyfin)
        self.cur = None             # the item playing
        self.queue, self.qi = [], 0
        self.pos = 0.0
        self.meta = {}
        self.paused = False
        self.shuffle = False
        self.volume = 80
        self.started = 0.0
        self.retry = None           # (args, target) to try if a stream fails at once
        self.next_query = 0.0
        self.next_status = 0.0
        self.status_sig = None
        self.confirm = (None, 0.0)  # system action waiting for a second press
        self.halting = 0.0          # shutting down: the screen says so until then (monotonic)
        self.halt_note = ""         # ...and says this if it's still here after that
        self.dirty = False
        self.msg, self.msg_until = None, 0.0
        self.fb = None
        self.ttyfd = None
        self.prev_vt = "1"
        self.prober = self.thumber = self.sysloop = None
        self.thumbs = {}            # path -> small PIL image (most recent ~300)
        self.cwd = home_dir()
        self.dir_sel = {}           # folder -> selected row
        self.show_hidden = False
        self.computers = Computers()  # Files > Other computers: their folders, opened on this Pi
        self.net_busy = None         # ...what the network is being asked, for the list to say so
        self.net_done = []           # ...its answers, for the screen's thread (net_tick)
        self.net_token = 0
        self.net_seen = {}           # ...a folder on one -> (when, [(name, is folder, size)]) last looked at
        self.net_shares = {}         # ...a computer -> its shared folders
        self.net_want = {}           # ...a folder -> the row to pick when its list comes
        self.net_changed = False     # ...the web page added or forgot one
        self.net_shown = {}          # ...a file the web page is showing: what it is (looked at on its thread)
        self.camera = Camera()
        self.camera.on_select = self.camera_select
        self.cam_list = False        # the Camera tab shows your cameras rather than one's picture
        self.cam_sel = 0
        self.cam_bot = None          # what the bot said it sees (SELECT): {"addr", "busy", "text", ...}
        self.friend = Friend()
        self.friend.facts = self.friend_facts
        self.friend.look = self.friend_look
        self.friend.snap = self.friend_snap
        self.friend.on_change = self.friend_changed
        self.friend.on_reply = self.bot_replied
        self.voice = Voice()
        self.voice.on_change = self.friend_changed
        self.voice.on_ready = self.voice_ready
        self.voice_want = None       # a voice you picked that's on its way
        self.voice_arrived = None    # ...and here (for the main loop to use)
        self.voice_told = ""         # the last of the voice's troubles shown
        self.coder = Coder()         # the Bot at work: your coding agent, acted out
        self.coder.on_change = self.coder_changed
        self.coder.on_news = self.coder_news
        self.coder.sound_ok = self.coder_may_sound
        self.coder_help = False      # its card on connecting an agent (START)
        self.coder_where = None      # ...and what that says: the web page's addresses, whether it has a password
        self.coder_base = (None, None, None)        # the tab without the coder: (what it shows, it, behind the coder)
        self.coder_shown = (None, None, 0.0, 0.0)   # the last frame: (that, the screen's count, when, when whole)
        self.coder_next = 0.0        # when its next frame is due
        self.prompts = AgentPrompts()  # prompts for your coding agent, typed here (A on the Bot at work)
        self.prompts.on_taken = self.prompt_taken
        self.prompt_draft = ""       # ...one you haven't sent yet
        self.sims = {}               # the Simulator tab's sims, by key (each made the first time it's opened)
        self.brain = SnakeBrain()     # Snake's AI: a decision model on your bot's computer
        self.brain_asked = None       # (game, step, round) it was last asked about
        self.brain_round = 0          # (one more each time it wakes up: an answer from before isn't used)
        self.brain_frame = 1.0 / SIM_FPS  # seconds a frame takes, of late (an answer's used on the next)
        self.brain_warned = set()     # models it's said can't keep up
        self.brain_server = ""        # ...on which computer
        self.brain_looking = False    # it's asking which decision models there are
        self.game = None             # one of your own games, while it runs (pitato/games.py)
        self.game_menu = None        # ...its menu (HOME): {"sel", "confirm", "bg"}
        self.game_since = 0.0        # ...when it was started
        self.stick_sent = {}         # ...where its sticks are, as last sent (an N64 or PSP game): (player, axis)
        self.game_players = {}       # ...each controller's player in it (its path -> 0 for player 1, 1...)
        self.input_pad = None        # the controller a press is from, while it's handled (None: the web page)
        self.ds_dirs = set()         # ...a DS game's: the directions its left stick has pressed (its d-pad)
        self.art_finder = None       # finding the games' pictures (Y on the Games tab), once asked
        self.game_pics = {}          # the games' pictures, ready to draw
        self.sim_opts = None         # a sim's START card: the row picked on it, or None
        self.sim_t = None            # when the sim on screen last moved on
        self.sim_next = 0.0          # when its next frame is due
        self.sim_base = (None, None, None)       # what doesn't move: (what it shows, it, the box's corners)
        self.sim_panel = (None, None, 0.0)       # the numbers beside the box: (what they show, them, when)
        self.sim_card = (None, None)             # a card over the box: (what it says, it)
        self.sim_shown = (None, None, 0.0, 0.0)  # the last frame: (that, the screen's count, when, when whole)
        self.sim_head = (None, None)             # the status bar and tabs: (what they show, them)
        self.sim_feet = {}                       # the buttons along the bottom, for each set of them
        self.sim_still = (None, None)            # the numbers' words: (what they say, them)
        self.sim_tiles = {}                      # pictures of words and figures, kept
        self.sim_mask = None                     # the round corners of a picture beside the box
        self.friend_scroll = 0       # how far back the conversation is scrolled (pixels)
        self.friend_seen = len(self.friend.log)
        self.friend_opened_at = 0.0
        self.friend_jitter = 1.0     # its remarks come not quite on the dot
        self.friend_more = None      # the Bot page's X menu, when open: {"sel": n}
        self.friend_pics = {}        # a picture's id -> (it, its rounded corners) as the Bot page shows it
        self.friend_work_shown = None    # what the chat said about your coding agent, last it was drawn
        self.pie = PieInk(cameras=self.pie_cameras)   # PiE-ink on another Pi: asked first for what it has
        self.camera.on_pie = self.pie.hear
        self.crypto = Crypto(self.pie)   # the Finance tab's coins (CoinGecko)
        self.stocks = Stocks()       # ...and its stocks (Yahoo Finance)
        self.fin_card = 0            # the card on the Finance tab: its stocks', then its coins'
        self.fin_auto = False
        self.fin_list = False        # the Finance tab shows your stocks and coins and the search for more (Y)
        self.fin_sel = 0
        self.fin_query = ""          # what you looked up last
        self.fin_found = None        # ...what it found: [{"kind", "id", "symbol", "name", ...}] (None: not yet)
        self.fin_status = None       # "Looking…", or why it couldn't
        self.fin_token = 0           # (a search's answer is used only if it's the latest)
        self.last_shot = None        # a picture the Camera tab just saved, to select in Photos
        self.hass = HomeAssistant()
        self.lights = HomeLights()   # the Lights page, through the same Home Assistant
        self.lights_scenes = False   # ...showing your scenes
        self.lights_hit = 0.0        # ...when an arrow last dimmed one
        self.home_sel = 0            # the icon picked on the home screen
        self.wall = (None, None)     # (what it's for, the home screen's background)
        self.home_base = (None, None)  # (what it's for, that background with the app cards on it)
        self.np_until = 0.0          # what's playing shows on the home screen until then (monotonic)
        self.gpi_case = gpi_case_set_up()   # a GPi Case's speaker: given silence in the terminal (player.py)
        self.pi_slow = slow_pi()     # a Pi Zero, 1, 2 or 3: on a TV, the Simulator and the Bot at work go slower
        self.hush_proc = None        # ...aplay, playing it
        self.hush_wait = 0.0         # ...not tried again before then, if it wouldn't play
        self.queue_random = False    # the queue playing is the start-up's random songs (shuffled again each round)
        self.resume_later = None     # (queue, index, seconds in): music a game or a video stopped, to come back
        self.resume_at_t = None      # ...when (monotonic)
        self.sound_used = None       # where what's playing sends its sound: (its route, the Bluetooth headphones')
        self.game_sound = None       # ...and the game's
        self.sound_look = 0.0        # ...looked at again then (Bluetooth headphones come and go)
        self.start_paused = False    # the next player starts paused, silent (the headphones it played through went)
        self.muted = False           # ...the player is that: its volume back as it plays on
        self.settling = False        # ...not paused yet (mplayer drops what it's told as it fills its cache)
        self.settle_play = False     # ...played on before it was: not playing yet
        self.settle_ask = 0.0        # ...told again then
        self.pause_said = None       # (the player, "yes" or "no"): whether it said it's paused, last it was asked
        self.set_sel = 0             # Settings: the row picked
        self.set_page = "root"       # Settings: "root" or "location"
        self.loc_results, self.loc_status = [], None
        self.wifi = {"nets": [], "saved": {}, "status": None, "busy": False, "radio": True, "ssid": "",
                     "ssid_t": 0.0}
        self.bt = Bluetooth()        # Settings > Bluetooth, and the web page's: pitato/bluetooth.py
        self.bt.on_change = self.bt_changed
        self.bt.sound_note = self.bt_sound_note
        self.bt_pick = None          # ...the device picked on its page (None: the switch)
        self.bt_at = 0               # ...and its row, last it was drawn
        self.picking = None          # "wallpaper" while a picture is being picked in Photos
        self.kb = None               # the on-screen keyboard, while it's up
        self.keyreader = KeyReader()
        self.weather = None          # made once the settings are loaded
        self.wx_page = 0             # Weather: now, the week, the forecast in words
        self.wx_icons = {}
        self.radio_stack = []        # Radio: folders opened (genre, popular, search)
        self.chan_stack = {}         # Cartoons, Free Movies...: tab -> the folder opened (Anime, a search)
        self.live_wait = {}          # News, Sports: tab -> "loading" or "error" while Plex's channels come
        self.vsize = None            # the playing video's size, for Full screen
        self.bars_for = None         # the video whose black bars have been drawn
        self.now_from = "list"       # where B goes from Now playing
        self.icons = {}              # drawn app icons
        self.remote_more = None      # the TV Remote's More menu, when open: {"sel": n}
        self.remote_pad = None       # the TV Remote's number pad, when open: {"text", "r", "c"}
        self.remote_hit = ("", 0.0)  # the button just pressed there, and when
        self.cam_said = ("", 0.0)    # the camera's last message and when it changed
        self.fin_next = 0.0
        self.shrinker = Shrinker(enabled=lambda: self.setting("shrink") != "Leave them")
        self.shrinker.on_done = self.video_shrunk   # (it starts when the service does: app.main)
        self.videos_changed = False  # a video was swapped for its smaller copy: the Videos tab, again
        self.shrink_drawn = 0.0      # when the Videos tab last showed how far that's got
        self.plex = Plex()
        self.plex_stack = []        # Plex folders you've opened, top is on screen
        self.plex_session = None
        self.plex_base = 0.0        # where the current Plex stream started
        self.plex_mode = None       # whether mplayer reports absolute or relative time
        self.plex_last = 0.0
        self.plex_pending = None    # seek target waiting for more presses
        self.plex_pending_t = 0.0
        self.next_timeline = 0.0
        self.plexthumber = None
        self.plex_live = (0.0, [])  # (when fetched, channels)
        self.jellyfin = Jellyfin()
        self.jf_stack = []          # Jellyfin folders you've opened, top is on screen
        self.jfthumber = None
        self.learn = None           # Settings > Controller: setting up a controller's buttons
        self.pads = None            # the controllers plugged in (the input loop sets this)
        self.pad_used = None        # ...the one last pressed: Settings > Swap A and B changes its buttons
        self.shot = (None, b"", "")  # the last picture of the screen sent to the web page
        self.web_radio_cache = {}   # Radio Browser lists the web page asked for
        self.web_icons = {}
        self.web_guard = False      # the web page is at the controls: your home folder only
        self.lock = threading.Lock()
        self.state = {"pos": {}, "dur": {}, "settings": {}, "radio": {}, "cam_turn": {}, "cam_flip": {}}
        self.fonts = None
        self.load_state()
        self.camera.turns = self.state["cam_turn"]   # (a camera's picture turned: kept with the rest)
        self.camera.flips = self.state["cam_flip"]   # (...one steered with left and right swapped, too)
        self.boot_media = self.setting("start") == "Home screen"
        self.res_boot()                                # (just restarted at a new resolution: it asks if you'll keep it)
        self.boot_song = time.monotonic() + BOOT_SONG_WAIT if self.setting("start_song") == "On" else 0.0
        set_accent(self.setting("accent"))
        self.weather = Weather(lambda: self.setting("location"),
                               lambda: "C" if self.setting("units") == "°C" else "F", pie=self.pie)
        self.weather.on_change = self.weather_drawn

    # -- settings ------------------------------------------------------------
    def setting(self, key):
        v = self.state["settings"].get(key)
        if key == "screen" and v not in SCREEN_MODES:
            return "Full screen" if v == "Fill" else "Fit"          # "Fill" is its old name
        if key == "home_style" and v in HOME_STYLE_WAS:
            return HOME_STYLE_WAS[v]                                # (what the styles were called at first)
        return SETTINGS_DEFAULT.get(key) if v is None else v

    def set_setting(self, key, value):
        self.state["settings"][key] = value
        if key == "accent":
            set_accent(value)
            self.icons.clear()
        if key in ("wallpaper", "picture"):
            self.wall = (None, None)
        if key == "shrink":
            self.shrinker.poke()
        self.save_state()
        self.dirty = True

    def clock_text(self, t=None, ampm=True):
        t = t or time.localtime()
        if self.setting("clock") == "24-hour":
            return time.strftime("%H:%M", t)
        return time.strftime("%-I:%M %p" if ampm else "%-I:%M", t)

    # -- saved state ---------------------------------------------------------
    def load_state(self):
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
            for k in self.state:
                self.state[k].update(s.get(k, {}))
            self.volume = int(s.get("volume", self.volume))
        except (OSError, ValueError):
            pass

    def save_state(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with _SAVING:                              # (two at once would write into one file together)
                with self.lock:
                    data = json.dumps(dict(self.state, volume=self.volume))
                tmp = f"{STATE_FILE}.{os.getpid()}.tmp"
                with open(tmp, "w") as f:
                    f.write(data)
                os.replace(tmp, STATE_FILE)
        except OSError:
            pass

    def length(self, it):
        if it["kind"] not in ("video", "audio") or "://" in it["src"]:
            return None
        entry = self.state["dur"].get(it["key"])
        try:
            mtime = os.path.getmtime(it["src"])
        except OSError:
            return None
        return entry[1] if entry and entry[0] == mtime else None

    def resume_at(self, it):
        """Seconds to resume a video from, or 0. -1 in state means watched."""
        if it["kind"] != "video":
            return 0
        p = self.state["pos"].get(it["key"], 0)
        n = self.length(it) or 0
        if p > 5 and (not n or p < n - 10):
            return p
        return 0

    def toast(self, text, secs=4):
        self.msg, self.msg_until = text, time.monotonic() + secs
        self.dirty = True

    def video_shrunk(self, old, new):
        """A video swapped for its smaller copy (on the shrinker's thread): where you were in it, and its length,
        go with it."""
        if new != old:
            with self.lock:
                for k in ("pos", "dur"):
                    if old in self.state[k]:
                        self.state[k][new] = self.state[k].pop(old)
            self.save_state()
        self.videos_changed = True

    # -- tabs ----------------------------------------------------------------
    def tab_items(self, i=None):
        return self.items.get(self.tab if i is None else i, [])

    def tab_type(self, i=None):
        return LIBRARY[self.tab if i is None else i]["type"]

    def tab_index(self, ttype):
        return next((i for i, t in enumerate(LIBRARY) if t["type"] == ttype), None)

    @staticmethod
    def parent_of(i):
        """The tab a tab lives inside (TV for Plex, say), or None."""
        name = LIBRARY[i].get("parent")
        return next((k for k, t in enumerate(LIBRARY) if t["name"] == name), None) if name else None

    @staticmethod
    def visible_tabs():
        return [i for i, t in enumerate(LIBRARY) if not t.get("parent")]

    def strip_tab(self):
        """The tab lit up along the top: the group, while you're inside it."""
        p = self.parent_of(self.tab)
        return self.tab if p is None else p

    def holds_buttons(self):
        """Pages that follow buttons held down themselves (no key repeat)."""
        return self.on_camera_page() or self.on_mandel_page() or (
            self.on_sim_page() and self.sim_opts is None and getattr(SIMS.get(LIBRARY[self.tab].get("sim")), "holds", False))

    def tick_limit(self):
        """How long the input loop may wait before the next tick."""
        if self.on_sim_page() and self.sim_opts is None:
            return max(0.0, min(0.05, self.sim_next - time.monotonic()))   # (its next frame)
        return 0.1 if self.on_camera_page() or self.on_coder_page() else 0.25

    def load_tab(self, i):
        tab = LIBRARY[i]
        if tab["type"] == "files":
            self.items[i] = [item(p, title_of(p), tab["kind"], p)
                             for p in find_files(tab["dirs"], tab["exts"])]
            if tab["kind"] == "video":
                self.shrinker.poke()                   # (any new ones too big for this Pi: made smaller)
        elif tab["type"] == "photos":
            files = find_files(tab["dirs"], IMAGE_EXTS)
            files.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                       reverse=True)          # newest first
            self.items[i] = [item(p, os.path.basename(p), "image", p) for p in files]
            if self.last_shot in files:       # the picture just taken on the Camera tab
                self.sels[i] = files.index(self.last_shot)
                self.last_shot = None
            if self.active and not (self.thumber and self.thumber.is_alive()):
                self.thumber = threading.Thread(target=self.thumb_loop, daemon=True)
                self.thumber.start()
        elif tab["type"] == "group":
            rows = []
            for name in tab["children"]:
                ci = next(k for k, t in enumerate(LIBRARY) if t["name"] == name)
                rows.append(dict(item("grp:" + name, name, "child", str(ci),
                                      sub=LIBRARY[ci].get("about", "")),
                                 icon=LIBRARY[ci].get("badge", "")))
            self.items[i] = rows
        elif tab["type"] == "radio":
            if self.radio_stack:
                self.items[i] = self.radio_stack[-1]["items"]
            else:
                self.items[i] = self.radio_root(tab)
        elif tab["type"] == "streams":
            self.items[i] = read_streams(tab["files"])
        elif tab["type"] == "browser":
            if self.web_guard and not self.web_may_see(self.cwd):
                self.cwd = home_dir()                  # the web page keeps to your home folder
            self.items[i] = self.list_dir(self.cwd)
            self.sels[i] = self.dir_sel.get(self.cwd, self.first_row(self.items[i]))
        elif tab["type"] == "plex":
            if self.plex.ready:
                if self.plex_stack:
                    self.items[i] = self.plex_stack[-1]["items"]
                elif self.status.get(i) != "loading":
                    self.plex_open("root", "Plex")
                self.start_plex_thumbs()
            else:
                self.items[i] = []
        elif tab["type"] == "jellyfin":
            if self.jellyfin.ready:
                if self.jf_stack:
                    self.items[i] = self.jf_stack[-1]["items"]
                elif self.status.get(i) != "loading":
                    self.jf_open("root", "Jellyfin")
                self.start_jf_thumbs()
            else:
                self.items[i] = []
        elif tab["type"] == "finance":
            self.fin_load()
            self.crypto.on_change = self.stocks.on_change = self.fin_changed
            cards = self.fin_cards()
            self.fin_card = min(self.fin_card, max(len(cards) - 1, 0))
            self.fin_focus()
            if self.active and self.tab == i and self.view == "list":
                self.fin_start()
            self.items[i] = []
        elif tab["type"] == "remote":
            self.hass.load(tab["files"], pick=self.setting("ha_tv") or "")
            self.hass.on_change = self.remote_changed
            self.hass.on_note = lambda text: self.toast(text, 3)
            self.hass.on_pick = lambda entity: self.set_setting("ha_tv", entity)   # (the TV picked, kept)
            if self.active and self.tab == i and self.view == "list":
                self.hass.start()
            self.items[i] = []
        elif tab["type"] == "lights":
            self.lights.load(tab["files"])
            self.lights.on_change = self.lights_changed
            self.lights.on_note = lambda text: self.toast(text, 3)
            if self.active and self.tab == i and self.view == "list":
                self.lights.start()
            self.items[i] = self.lights_rows()
        elif tab["type"] == "weather":
            self.weather.refresh(full=self.active and self.tab == i and self.view == "list")
            self.items[i] = []
        elif tab["type"] == "friend":
            self.friend.load(tab["files"])
            self.items[i] = []
            if self.active and self.tab == i and self.view == "list" and self.bot_mode() == "chat":
                self.friend_opened()
        elif tab["type"] == "camera":
            self.friend.load(self.friend_files())     # (SELECT: the bot, if there's one)
            self.camera.load(tab["files"], last=self.state.get("camera"))
            self.camera.on_change = self.camera_changed
            self.camera.on_saved = self.picture_saved
            if not self.camera.addr:
                self.cam_list = True
            if self.active and self.tab == i and self.view == "list":
                if self.cam_list:
                    self.camera.scan()
                else:
                    self.camera.start()
            self.items[i] = []
        elif tab["type"] == "games":
            self.items[i] = self.games_rows()
        elif tab["type"] == "sim":
            self.items[i] = []
            self.sim_t = None                          # (it waited while you were away)
            if tab.get("sim") == "snake":
                self.snake_models()                    # (the decision models on your bot's computer, for its AI)
        elif tab["type"] == "system":
            self.items[i] = system_info()
            if not (self.sysloop and self.sysloop.is_alive()):
                self.sysloop = threading.Thread(target=self.system_loop, daemon=True)
                self.sysloop.start()
        elif tab["type"] == "channels" and self.chan_stack.get(i):
            self.items[i] = self.chan_stack[i][-1]["items"]
        elif tab["type"] == "channels":
            self.load_channels(i)
        n = len(self.tab_items(i))
        self.sels[i] = min(self.sels.get(i, 0), max(n - 1, 0))

    def switch_tab(self, d):
        if self.tab_type() == "camera":
            self.camera.stop()
        if self.tab_type() == "finance":
            self.fin_stop()
            self.fin_close()
        if self.tab_type() == "remote":
            self.hass.stop()
            self.remote_more = None
        if self.tab_type() == "lights":
            self.lights_close()
        self.confirm = (None, 0.0)
        self.picking = None                            # (picking a picture: not any more)
        self.friend_more = None
        self.coder_help = False
        self.sim_close()
        vis = self.visible_tabs()
        self.tab = vis[(vis.index(self.strip_tab()) + d) % len(vis)]
        self.load_tab(self.tab)

    def system_loop(self):
        si = self.tab_index("system")
        while self.active and self.tab == si:
            time.sleep(2)
            if self.active and self.tab == si and self.view == "list" and not self.proc_owns_screen():
                self.items[si] = system_info()
                self.dirty = True

    def list_dir(self, path):
        if self.is_net(path):
            return self.net_list(path)
        out = []
        try:
            entries = list(os.scandir(path))
        except OSError:
            self.toast("Can't open that folder")
            entries = []
        guard = self.web_guard
        if path != "/" and not (guard and os.path.realpath(path) == os.path.realpath(home_dir())):
            out.append(item(os.path.dirname(path.rstrip("/")) or "/", "..", "up",
                            os.path.dirname(path.rstrip("/")) or "/"))
        if os.path.realpath(path) == os.path.realpath(home_dir()):
            out.append(self.net_row())
        dirs, files = [], []
        for en in entries:
            if en.name.startswith(".") and (guard or not self.show_hidden):
                continue
            if guard and web_private(en.name):
                continue
            try:
                is_dir = en.is_dir()
            except OSError:
                continue
            (dirs if is_dir else files).append(en)
        for en in sorted(dirs, key=lambda x: x.name.lower()):
            out.append(item(en.path, en.name, "dir", en.path))
        for en in sorted(files, key=lambda x: x.name.lower()):
            out.append(item(en.path, en.name, classify(en.path), en.path))
        return out

    def web_may_see(self, path):
        """What the web page may open: things in your home folder or on your other computers, not hidden,
        not private."""
        if path.startswith(NET):
            return True
        root = self.computers.root
        if os.path.normpath(path).startswith(root + "/"):
            if self.computers.owner(path) is None:     # (only the computers on the list)
                return False
            parts = os.path.relpath(os.path.normpath(path), root).split(os.sep)
            return not any(x.startswith(".") for x in parts) and not web_private(parts[-1])
        home = os.path.realpath(home_dir())
        real = os.path.realpath(path)
        if real != home and not real.startswith(home + os.sep):
            return False
        parts = [] if real == home else os.path.relpath(real, home).split(os.sep)
        return not any(x.startswith(".") for x in parts) and not (parts and web_private(parts[-1]))

    def browse(self, path, select=None):
        if self.web_guard and not self.web_may_see(path):
            path, select = home_dir(), None            # the web page keeps to your home folder
        bi = self.tab_index("browser")
        self.dir_sel[self.cwd] = self.sels.get(bi, 0)
        self.cwd = path
        self.items[bi] = self.list_dir(path)
        sel = self.dir_sel.get(path, self.first_row(self.items[bi]))
        if select:
            found = next((k for k, it in enumerate(self.items[bi]) if it["src"] == select), None)
            if found is None and self.is_net(path):
                self.net_want[path] = select           # (its list is on its way: picked when it comes)
            sel = sel if found is None else found
        self.sels[bi] = min(sel, max(len(self.items[bi]) - 1, 0))
        self.tops[bi] = 0
        self.dirty = True

    @staticmethod
    def first_row(items):
        """Start on the first real entry rather than the '..' row (or Other computers)."""
        k = 1 if len(items) > 1 and items[0]["kind"] == "up" else 0
        return k + 1 if len(items) > k + 1 and items[k]["kind"] == "netroot" else k

    # -- mode ----------------------------------------------------------------
    def proc_owns_screen(self):
        """A video, or a game, is drawing on the screen: the menus keep off it."""
        return (bool(self.proc) and self.kind in SCREEN_KINDS) or (self.game is not None and self.view == "game")

    def enter(self):
        try:
            from PIL import Image, ImageDraw, ImageFont  # noqa: F401
            import numpy  # noqa: F401
            self.load_fonts()
            self.fb = Framebuffer()
        except Exception as ex:      # missing package or no framebuffer
            print(f"media mode unavailable: {ex}", flush=True)
            self.fb = None
            return
        self.active = True
        self.hush_stop()                               # (media mode needs no silence to keep its speaker quiet)
        self.camera.listen()                           # PiE-inks say they're there: asked first for what they have
        if self.view not in ("photo", "pdf", "text"):
            self.view = "home"
            apps = self.home_apps()
            self.home_sel = next((k for k, a in enumerate(apps) if a[1] == self.strip_tab()), 0)
        self.res_ask()                                 # (a new resolution, to keep or not)
        for i, tab in enumerate(LIBRARY):
            if tab["type"] not in ("channels", "camera", "system", "plex", "jellyfin") or i == self.tab:
                self.load_tab(i)
        try:
            vt = subprocess.run(["fgconsole"], capture_output=True, text=True)
            self.prev_vt = vt.stdout.strip() or "1"
        except OSError:
            pass
        subprocess.run(["chvt", str(MEDIA_VT)])
        try:
            self.ttyfd = os.open(f"/dev/tty{MEDIA_VT}", os.O_RDWR | os.O_NOCTTY)
            fcntl.ioctl(self.ttyfd, 0x4B3A, 1)   # KDSETMODE KD_GRAPHICS: no text/cursor
        except OSError:
            pass
        self.dirty = True
        if self.playing_now():                         # what's playing, for a moment
            self.pop_now()
        if not (self.prober and self.prober.is_alive()):
            self.prober = threading.Thread(target=self.probe_loop, daemon=True)
            self.prober.start()

    def leave(self):
        """Back to the terminal. Music and radio keep playing; video stops."""
        if not self.active:
            return
        if self.learn:                                 # the controller's buttons go back to keys
            self.cancel_learn("")
        self.picking = None                            # (nothing left half-open for next time)
        self.friend_more = None
        self.confirm = (None, 0.0)
        self.camera.stop()
        self.voice.stop(unload=True)
        self.fin_stop()
        self.fin_close()
        self.hass.stop()
        self.remote_more = None
        self.lights_close()
        if self.remote_pad is not None:
            self.close_pad()
        if self.view == "keys":
            self.close_keyboard(False)
        if self.kind not in LISTEN_KINDS:
            self.stop()
        self.active = False
        self.save_state()
        if self.ttyfd is not None:
            try:
                fcntl.ioctl(self.ttyfd, 0x4B3A, 0)   # KD_TEXT
                os.close(self.ttyfd)
            except OSError:
                pass
            self.ttyfd = None
        if self.fb:
            self.fb.close()
            self.fb = None
        subprocess.run(["chvt", self.prev_vt])

    def shutdown(self):
        self.hush_stop()
        self.stop()
        self.shrinker.stop()
        self.computers.close_all()
        self.close_viewer()
        self.camera.stop()
        if self.active and self.fb is not None and system_stopping():
            self.goodbye()                 # the Pi is going off (the power switch, say): say so
            return
        self.leave()

    def power_off(self):
        """The case's power switch is off: the Pi shuts down, as with Shut down in the menu. In
        media mode the screen says so; in the terminal the Pi's own shutdown lines show there."""
        if time.monotonic() < self.halting:
            return                                     # on its way already
        print("power switch: off, shutting down", flush=True)
        self.halting, self.halt_note = time.monotonic() + HALT_WAIT, "The Pi didn't shut down"
        try:
            if self.active and self.fb is not None:
                if self.learn:
                    self.cancel_learn("")
                self.stop()                            # (a video would draw over it)
                self.close_viewer()
                self.camera.stop()
                self.voice.stop(unload=True)
                self.goodbye()
            else:
                show_shutdown_lines()                  # first: systemd may be on its way already
                self.save_state()                      # (music stops as the service does)
        finally:
            if not system_stopping():                  # (unless systemd-logind saw it first)
                try:
                    subprocess.Popen(["systemctl", "poweroff"], stdin=subprocess.DEVNULL)
                except OSError as ex:
                    print(f"power switch: couldn't shut down ({ex})", flush=True)

    def goodbye(self):
        """'Shutting down' on the screen, left there until the power goes."""
        try:
            self.save_state()
            img, d = self.canvas()
            W, H = self.fb.w, self.fb.h
            d.text((W / 2, H / 2), "Shutting down", font=self.fonts["big"], fill=TEXT, anchor="mm")
            self.fb.show(img)
        except Exception:
            self.leave()

    # -- opening things ------------------------------------------------------
    def open_item(self, items, i):
        it = items[i]
        kind = it["kind"]
        if (self.web_guard and kind in FILE_KINDS and str(it.get("src", "")).startswith("/")
                and not self.web_may_see(it["src"])):
            self.toast("The web page can't open that", 3)
            return
        if (kind in FILE_KINDS and kind not in ("dir", "up") and self.is_net(str(it.get("src", "")))
                and not self.net_answers(it["src"])):
            self.toast("That computer isn't answering", 3)
            return
        if kind in ("dir", "up"):
            self.browse(it["src"], select=self.cwd if kind == "up" else None)
        elif kind in ("netroot", "netpc", "netadd", "netshare"):
            self.net_open(it)
        elif kind == "child":
            self.tab = int(it["src"])
            self.load_tab(self.tab)
        elif kind == "radiodir":
            self.radio_open(it["src"], it["title"])
        elif kind == "chdir":
            self.open_dir(self.tab, it)
        elif kind == "chplex":                          # off to Plex to sign in
            self.chan_stack[self.tab] = []
            self.tab = self.tab_index("plex")
            self.load_tab(self.tab)
        elif kind == "chretry":
            self.live_wait.pop(self.tab, None)
            self.load_tab(self.tab)
        elif kind == "chwait":
            pass
        elif kind == "chsearch":
            self.open_keyboard("Search channels", "", self.chan_search)
        elif kind == "plexsearch":
            live = it["src"] == "livesearch"
            self.open_keyboard("Search channels" if live else "Search Plex", "",
                               lambda q, live=live: self.plex_open(("livesearch:" if live else "search:") + q,
                                                                   f"“{q}”"))
        elif kind == "radiosearch":
            self.open_keyboard("Station name", "", lambda text: self.radio_open("search:" + text, f"“{text}”"))
        elif kind == "plexwant":
            self.toast("That one isn't on your Plex server")
        elif kind == "plexdir":
            self.plex_open(it["src"], it["title"], context=it.get("ptype", ""))
        elif kind == "jfsearch":
            self.open_keyboard("Search Jellyfin", "", lambda q: self.jf_open("search:" + q, f"“{q}”"))
        elif kind == "jfdir":
            self.jf_open(it["src"], it["title"])
        elif kind in ("video", "audio", "live", "radio", "plexvideo", "jfvideo"):
            same = [x for x in items if x["kind"] == kind]
            self.play(same, same.index(it))
        elif kind == "image":
            pics = [x["src"] for x in items if x["kind"] == "image"]
            self.open_photo(pics, pics.index(it["src"]))
        elif kind == "pdf":
            self.open_pdf(it["src"])
        elif kind == "doc":
            self.open_doc(it["src"])
        elif kind == "game":
            self.game_open(it)
        elif kind == "action":
            self.system_action(it)
        elif kind == "info":
            pass
        elif kind in ("other", "text") and self.game_system(it["src"]):   # a game, in Files (or from the web page):
            self.game_open(dict(it, system=self.game_system(it["src"])))  # (a .md may be a Mega Drive game's)
        elif kind == "text" or looks_like_text(it["src"]):
            self.open_text(it["src"])
        else:
            self.toast("Can't open this kind of file")

    def system_action(self, it):
        act = it["src"]
        waiting, until = self.confirm
        if waiting != act or time.monotonic() > until:
            self.confirm = (act, time.monotonic() + 4)
            self.dirty = True
            return
        self.confirm = (None, 0.0)
        if act == "plex_signout":
            self.plex.sign_out()
            self.plex_stack = []
            self.items[self.tab_index("plex")] = []
            self.toast("Signed out of Plex")
            return
        if act == "jellyfin_signout":
            self.jellyfin.sign_out()
            self.jf_stack = []
            self.items[self.tab_index("jellyfin")] = []
            self.toast("Signed out of Jellyfin")
            return
        self.halting = time.monotonic() + HALT_WAIT       # nothing draws over it
        self.halt_note = {"reboot": "The Pi didn't restart", "poweroff": "The Pi didn't shut down",
                          "restart": "Media mode didn't restart"}[act]
        self.render_wait({"reboot": "Rebooting", "poweroff": "Shutting down",
                          "restart": "Restarting media mode"}[act], "One moment")
        self.save_state()
        cmd = {"reboot": ["systemctl", "reboot"], "poweroff": ["systemctl", "poweroff"],
               "restart": ["systemctl", "restart", "pitato"]}[act]
        subprocess.Popen(cmd)

    def close_viewer(self):
        tmp = self.v.get("tmp")
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        self.v = {}
        self.view = "list"
        self.dirty = True

    def tick(self):
        """Called every loop: track position, move on when something ends."""
        now = time.monotonic()
        if self.net_done or self.net_changed:
            self.net_tick()
        self.shrinker.hold(bool(self.proc and self.kind in SCREEN_KINDS) or self.game is not None)
        if self.videos_changed:
            self.videos_changed = False
            vi = next((k for k, t in enumerate(LIBRARY) if t.get("kind") == "video"), None)
            if vi is not None:
                self.load_tab(vi)
                self.dirty = True
        if (self.shrinker.current and self.active and self.view == "list" and LIBRARY[self.tab].get("kind") == "video"
                and now - self.shrink_drawn >= 3):
            self.shrink_drawn = now                   # (how far it's got)
            self.dirty = True
        self.hush_tick(now)                           # (the GPi Case's speaker, quiet in the terminal)
        self.sound_tick(now)                          # (Bluetooth headphones come or go: the sound goes with them)
        self.settle_tick(now)                         # (a player started paused: paused once it listens)
        self.music_back(now)                          # (music a game or a video stopped, back after it)
        self.res_tick(now)                            # (a new resolution nobody said to keep: back it goes)
        self.bt.watch("screen", self.on_bt_page())    # (Bluetooth looked at while its page is open)
        if self.boot_song and now >= self.boot_song:   # Settings > Random song at start-up
            self.boot_song = 0.0
            self.random_song()
        if self.np_until and now >= self.np_until:     # what's playing has had its moment: the weather again
            self.np_until = 0.0
            if self.active and self.view == "home":
                self.dirty = True
        if self.game is not None or self.art_finder is not None:
            self.game_tick(now)
        if self.learn:
            self.learn_tick(now)
        note = getattr(self, "screen_note", None)
        if note and self.proc and self.kind not in LISTEN_KINDS and now - self.started > 1.5:
            self.screen_note = None
            if now < note[1]:
                self.osd(SCREEN_SAY.get(note[0], note[0]), 1500 if note[0] in SCREEN_SAY else 3500)
            if not self.vsize:
                self.cmd("pausing_keep_force get_video_resolution")
        if self.proc and self.active and self.fb and self.proc_owns_screen() and self.vsize \
                and now - self.started > 1 and self.proc.poll() is None:
            bars = (id(self.proc), self.vsize, self.setting("screen"))
            if bars != self.bars_for:
                self.bars_for = bars
                sw, sh = self.screen_dims()
                whole = fit_box(self.vsize, sw, sh, inset=0) if bars[2] == "Fit" else None
                if whole and whole != (0, 0, sw, sh) and hasattr(self.fb, "blank_outside"):
                    try:                                  # black bars, not the menu, round the picture
                        self.fb.blank_outside(fit_box(self.vsize, sw, sh))
                    except (OSError, ValueError, ZeroDivisionError):
                        pass
        if getattr(self, "next_vsize", False) and self.proc and now - self.started > 2:
            self.next_vsize = False
            self.cmd("pausing_keep_force get_video_resolution")
        if self.msg and now > self.msg_until:
            self.msg = None
            self.dirty = True
        if self.prompts.queue:                         # (prompts nobody took: yours again)
            self.prompt_expired()
        if self.confirm[0] and now > self.confirm[1]:
            self.confirm = (None, 0.0)
            self.dirty = True
        if self.halting and now >= self.halting:       # still here: it didn't go
            self.halting = 0.0
            self.toast(self.halt_note, 4)
        if self.active and self.view == "list" and self.tab_type() == "remote" \
                and 0.25 <= now - self.remote_hit[1] < 0.6:
            self.dirty = True                         # let the pressed button go dark again
        if self.active and (self.view == "home" or (self.view == "list" and self.tab_type() == "weather")):
            self.weather.refresh(full=self.view == "list")   # only does anything when it's due
        if self.voice_arrived:
            self.voice_use(self.voice_arrived)
        if self.voice.error and self.voice.error != self.voice_told:
            self.voice_told = self.voice.error
            if self.on_friend_page() or (self.view == "list" and self.tab_type() == "settings"
                                         and self.set_page in FRIEND_PAGES):
                self.toast(self.voice.error, 5)
        elif not self.voice.error:
            self.voice_told = ""
        if self.on_friend_page():
            fr = self.friend
            gap = fr.chatter() * 60
            if gap and fr.ready() and not fr.busy and \
                    time.time() - max(fr.last_said(), self.friend_opened_at) >= gap * self.friend_jitter:
                fr.remark(self.friend_topic())
                self.friend_jitter = random.uniform(0.7, 1.3)
        if self.on_camera_page():
            if self.camera.check_hold():
                self.dirty = True
            told = self.cam_bot
            if told and not told["busy"]:
                if told["spoken"] and self.voice.speaking:
                    told["until"] = max(told["until"], now + 3)
                elif told["until"] <= now < told["until"] + 1:
                    self.dirty = True                 # what the bot said has had its turn
            shot = self.camera.shot
            if shot and shot[2] + CAM_SHOT_SHOW <= now < shot[2] + CAM_SHOT_SHOW + 1:
                self.dirty = True                     # time to take the little picture away
            if self.camera.action and 3 <= now - self.cam_said[1] < 7:
                self.dirty = True                     # and a message that has had its turn
        if self.on_coder_page() and not self.coder_help and now >= self.coder_next:
            co = self.coder
            fps = 4 if co.asleep else CODER_FPS.get(co.anim, 6)
            if self.fb is not None and not getattr(self.fb, "same", True) and self.pi_slow:
                fps = min(fps, 5)                      # (a Pi Zero on a TV: each frame scaled up costs it more)
            self.coder_next = now + 1.0 / fps
            self.dirty = True
        if self.on_sim_page() and self.sim_opts is None and now >= self.sim_next:
            fps = SIM_FPS if self.fb is None or getattr(self.fb, "same", True) or not self.pi_slow else SIM_FPS_BIG
            nxt = self.sim_next + 1.0 / fps              # (a steady beat; behind, it starts again)
            self.sim_next = nxt if nxt > now else now + 1.0 / fps
            self.dirty = True
        if self.coder.heard and not self.setting("coder_seen"):
            self.set_setting("coder_seen", "yes")     # (an agent has found it: no more "how to connect")
        if (self.fin_auto and self.active and self.view == "list"
                and self.tab_type() == "finance" and now >= self.fin_next):
            self.press_finance("right", False)
        if self.plex.pin and self.active and self.tab_type() == "plex" and now >= self.next_status:
            self.dirty = True
        if self.jellyfin.quick and self.active and self.tab_type() == "jellyfin" and now >= self.next_status:
            self.dirty = True                         # (how long its code is good for)
        if self.active and now >= self.next_status and self.view in self.STATUS_VIEWS:
            self.next_status = now + 2
            sig = self.status_signature()
            if sig != self.status_sig:
                self.status_sig = sig
                self.dirty = True
        v = self.v
        if self.view == "photo" and v.get("slideshow") and now >= v["next_t"]:
            self.photo_step(1)
            v["next_t"] = now + SLIDESHOW_SECS
        if self.view == "wait" and v.get("result"):
            if v["result"] == "fail":
                src = v["src"]
                self.close_viewer()
                try:
                    self.open_text(src, text=doc_text(src))
                except Exception:
                    self.toast("Couldn't open this document")
            else:
                self.open_pdf(v["result"], v["title"])
        if not self.proc:
            return
        if self.kind == "plex" and self.proc.poll() is None:
            if self.plex_mode is None and self.pos >= 0:
                base = self.plex_base
                self.plex_mode = "abs" if base > 30 and self.pos >= base - 10 else "rel"
            if self.plex_mode:
                self.plex_last = self.plex_now()
            if self.plex_pending is not None and now >= self.plex_pending_t:
                target, self.plex_pending = self.plex_pending, None
                self.plex_restart(target)
                return
            if now >= self.next_timeline:
                self.next_timeline = now + PLEX_TIMELINE_SECS
                threading.Thread(target=self.vod(self.cur).timeline, daemon=True,
                                 args=(self.cur["src"], "paused" if self.paused else "playing",
                                       self.plex_now(), self.cur.get("dur")),
                                 kwargs={"session": self.plex_session}).start()
        if self.proc.poll() is not None and self.kind == "plex":
            it, quick = self.cur, now - self.started < 8
            pos, length = self.plex_now(), (self.cur or {}).get("dur") or 0
            done = bool(length) and pos > length * 0.9
            self.proc = None
            self.plex_finish(it, pos, self.plex_session, done)
            self.kind, self.cur = None, None
            if quick:
                self.toast(f"{self.vod_name(it)} couldn't play this one", 5)
            elif not done:
                self.toast("Playback stopped. Press A to pick up where you left off", 5)
            nxt = self.qi + 1
            if (done and it and it.get("ptype") == "episode" and nxt < len(self.queue)
                    and self.queue[nxt].get("series") == it.get("series")):
                self.play_plex(self.queue, nxt, start=0)       # on to the next episode
            else:
                self.view = "list"
                self.dirty = True
            return
        if self.proc.poll() is not None:
            was = self.kind
            quick = now - self.started < 8
            self.proc = None
            if quick and self.retry:              # try the backup way once
                args, target = self.retry
                self.retry = None
                self.start_paused = self.muted        # (paused and silent, as that one was)
                try:
                    self.spawn(args, target)
                finally:
                    self.start_paused = False
                return
            online = bool(self.cur) and self.cur["src"].startswith("ia:")
            self.remember(finished=not quick)
            i = None if was in ("live", "radio") or (quick and online) else self.next_index(1)
            if was in ("live", "radio") and quick:
                self.toast("Couldn't play that stream")
            elif quick and online:                      # not on to the next: it'd likely fail too
                self.toast("Couldn't play that one. Check the WiFi, or try another", 5)
            if i is not None:
                self.play(self.queue, i, show=False)  # (on to the next, wherever you are)
            else:
                self.kind = None
                if was not in LISTEN_KINDS or self.view == "now":
                    self.view = "list"
                self.dirty = True
        elif now >= self.next_query and self.kind in ("audio", "video", "plex"):
            self.cmd("pausing_keep_force get_time_pos")
            self.next_query = now + (1 if self.kind == "audio" else 2)
            if self.kind == "audio" and self.view == "now":
                self.dirty = True

    def release(self, name):
        """Button let go: stops the camera turning or zooming, or the Mandelbrot Set moving, or goes to
        the game."""
        if self.view == "game":
            self.release_game(name)
            return
        if self.on_camera_page():
            self.camera.release(name)
            self.dirty = True
        s = self.sims.get("mandel")
        if s is not None:
            s.release(name)

    def press(self, name, repeat=False):
        """Returns 'exit' when media mode should close."""
        if self.view == "keepres":                     # a new resolution: keep it, or go back
            return self.press_keep_res(name, repeat)
        if self.view == "learn":                       # (controllers come in through learn_event)
            if name == "b" and not repeat:
                self.cancel_learn()
            return None
        if self.view == "game":                        # the buttons are the game's (HOME: its menu)
            return self.press_game(name, repeat)
        if self.view == "gamemenu":
            return self.press_game_menu(name, repeat)
        if self.proc and self.kind == "plex":
            length = (self.cur or {}).get("dur") or 0
            if name == "a":
                self.cmd("pause")
                self.paused = not self.paused
                self.osd(("Paused  " if self.paused else "")
                         + f"{clock(self.plex_now())} of {clock(length)}", 1500)
                threading.Thread(target=self.vod(self.cur).timeline, daemon=True,
                                 args=(self.cur["src"], "paused" if self.paused else "playing",
                                       self.plex_now(), length), kwargs={"session": self.plex_session}).start()
            elif name == "b":
                self.stop()
                self.dirty = True
            elif name in ("left", "right", "l", "r"):
                self.plex_seek({"left": -10, "right": 10, "l": -60, "r": 60}[name])
            elif name == "y":
                self.next_screen()
            elif name == "x":
                left = f",  {clock(length - self.plex_now())} left" if length else ""
                self.osd(f"{clock(self.plex_now())} of {clock(length)}{left}", 2500)
            elif name in ("up", "down"):
                self.set_volume(VOLUME_STEP if name == "up" else -VOLUME_STEP)
            elif name == "start":
                self.skip(1)
            elif name == "select":
                self.skip(-1)
            return None

        if self.proc and self.kind in ("video", "live"):
            if name == "a":
                self.cmd("pause")
                self.cmd("pausing_keep_force osd_show_progression")
                self.paused = not self.paused
            elif name == "b":
                self.stop()
                self.dirty = True
            elif name == "start":
                self.skip(1)
            elif name == "select":
                self.skip(-1)
            elif name in ("up", "down"):
                self.set_volume(VOLUME_STEP if name == "up" else -VOLUME_STEP)
            elif name == "y" and not repeat:
                self.next_screen()
            elif name in PLAYING:
                self.cmd("pausing_keep " + PLAYING[name])
            return None

        if self.view == "home":
            return self.press_home(name, repeat)
        if self.view == "keys":
            return self.press_keys(name, repeat)
        if self.view == "help":
            if not repeat:
                back = self.help_from
                self.view = back if back != "now" or self.kind in LISTEN_KINDS else "list"
                self.dirty = True
            return None
        if self.view == "wait":
            if name == "b":
                self.close_viewer()
            return None
        if self.view == "photo":
            return self.press_photo(name, repeat)
        if self.view == "pdf":
            return self.press_pdf(name, repeat)
        if self.view == "text":
            return self.press_text(name, repeat)

        if self.view == "now" and self.kind in LISTEN_KINDS:
            if repeat:
                return None
            radio = self.kind == "radio"
            if name == "a":
                self.cmd("pause")
                self.paused = not self.paused
            elif name in ("left", "right") and not radio:
                self.cmd(f"seek {10 if name == 'right' else -10} 0")
                self.paused = False
            elif name in ("l", "select") or (radio and name == "left"):
                self.skip(-1)
            elif name in ("r", "start") or (radio and name == "right"):
                self.skip(1)
            elif name in ("up", "down"):
                self.set_volume(VOLUME_STEP if name == "up" else -VOLUME_STEP)
            elif name == "y" and not radio:
                self.shuffle = not self.shuffle
            elif name == "x":
                self.view, self.help_from = "help", "now"
            elif name == "b":
                self.view = "home" if self.now_from == "home" else "list"
            self.dirty = True
            return None

        return self.press_list(name, repeat)

    def press_list(self, name, repeat):
        items = self.tab_items()
        n = len(items)
        sel = self.sels.get(self.tab, 0)
        ttype = self.tab_type()
        grid = ttype == "photos"
        cols = self.grid_cols() if grid else 1
        page = self.grid_rows() * cols if grid else self.visible_rows()

        if ttype == "remote":
            r = self.press_remote(name, repeat)
            if r != "pass":
                return r
        if ttype == "lights":
            r = self.press_lights(name, repeat)
            if r != "pass":
                return r
        if ttype == "settings":
            r = self.press_settings(name, repeat)
            if r != "pass":
                return r
        if ttype == "camera":
            r = self.press_cameras(name, repeat)
            if r != "pass":
                return r
        if ttype == "friend":
            r = self.press_bot(name, repeat)
            if r != "pass":
                return r
        if ttype == "sim":
            r = self.press_sim(name, repeat)
            if r != "pass":
                return r
        if ttype == "games" and name == "y":
            if not repeat:
                self.games_find_art()
            return None
        if ttype == "finance" and self.fin_list:
            r = self.press_fin_list(name, repeat)
            if r != "pass":
                return r
        if ttype == "photos" and self.picking == "bot" and name in ("a", "b") and not repeat:
            path = items[sel]["src"] if name == "a" and n else None
            self.picking = None
            self.tab = self.tab_index("friend")         # (back as it was: no hello in the way)
            self.friend.load(self.friend_files())
            if path:                                   # a word with it, or none: it's sent either way
                self.open_keyboard("Ask about this picture, or just send it", "",
                                   lambda text, path=path: self.friend_send(text, path), empty=True, limit=200)
            self.dirty = True
            return None
        if ttype == "photos" and self.picking == "wallpaper" and name in ("a", "b") and not repeat:
            if name == "a" and n:
                self.set_setting("picture", items[sel]["src"])
                self.set_setting("wallpaper", "Picture")
                self.toast("Background set", 2)
            self.picking = None
            self.tab = self.tab_index("settings")
            self.load_tab(self.tab)
            self.dirty = True
            return None
        if ttype == "radio" and not repeat:
            if name == "y" and self.radio_stack and n and items[sel]["kind"] == "radio":
                self.radio_save(items[sel])
                return None
            if name == "a" and self.radio_stack and not n and self.status.get(self.tab) in ("error", None):
                folder = self.radio_stack.pop()
                self.radio_open(folder["key"], folder["title"])
                return None
        if ttype == "channels" and not n and name == "a" and not repeat:
            stack = self.chan_stack.get(self.tab)
            if self.status.get(self.tab) == "error" and stack and stack[-1].get("src"):
                gone = stack.pop()                              # try that folder again
                self.open_dir(self.tab, {"title": gone["title"], "src": gone["src"]})
            elif self.status.get(self.tab) == "error":         # try again
                self.status.pop(self.tab, None)
                self.load_tab(self.tab)
            elif self.status.get(self.tab) == "noplex":        # off to Plex to sign in
                self.chan_stack[self.tab] = []
                self.tab = self.tab_index("plex")
                self.load_tab(self.tab)
            self.dirty = True
            return None
        if name == "b":
            if ttype == "plex" and self.plex_back():
                return None
            if ttype == "jellyfin" and self.jf_back():
                return None
            if ttype == "radio" and self.radio_back():
                return None
            if ttype == "channels" and self.chan_back(self.tab):
                return None
            if ttype == "browser" and self.is_net(self.cwd):
                self.browse(self.net_up(self.cwd), select=self.cwd)
                return None
            if ttype == "browser" and self.cwd.rstrip("/") != home_dir() and self.cwd != "/":
                self.browse(os.path.dirname(self.cwd.rstrip("/")) or "/", select=self.cwd)
                return None
            parent = self.parent_of(self.tab)
            if parent is not None:                    # back out to the TV menu
                if ttype == "remote":
                    self.hass.stop()
                    if self.remote_pad is not None:
                        self.close_pad()
                if ttype == "lights":
                    self.lights_close()
                self.chan_stack[self.tab] = []
                child = LIBRARY[self.tab]["name"]
                self.tab = parent
                self.load_tab(parent)
                self.sels[parent] = next((k for k, it in enumerate(self.items[parent])
                                          if it["title"] == child), 0)
                self.dirty = True
                return None
            self.go_home()
            return None
        if name in ("l", "r"):
            if not repeat:
                self.switch_tab(1 if name == "r" else -1)
                self.dirty = True
            return None
        if ttype == "plex":
            st = self.status.get(self.tab)
            if not self.plex.ready:
                if name == "a" and not repeat and st not in ("code", "finding") and not self.plex.pin:
                    self.plex_sign_in()
                return None
            if st == "loading":
                return None
            if not n and name == "a" and not repeat:
                self.plex_open("root", "Plex")
                return None
        if ttype == "jellyfin":
            st = self.status.get(self.tab)
            if not self.jellyfin.ready:
                if name == "a" and not repeat and st not in ("finding", "signing") and not self.jellyfin.quick:
                    self.jf_sign_in()
                return None
            if st == "loading":
                return None
            if not n and name == "a" and not repeat:
                self.jf_open("root", "Jellyfin")
                return None
        if ttype == "finance":
            return self.press_finance(name, repeat)
        if ttype == "weather":
            return self.press_weather(name, repeat)
        if name == "x":
            self.view, self.help_from = "help", "list"
        elif name == "y" and ttype == "browser" and self.cwd == NET:
            if n and items[sel]["kind"] == "netpc" and not repeat:
                self.net_forget(items[sel])
        elif name == "y" and ttype == "browser" and self.web_guard:
            self.toast("Hidden files stay hidden from the web page", 3)
        elif name == "y" and ttype == "browser":
            self.show_hidden = not self.show_hidden
            self.browse(self.cwd)
            self.toast("Showing hidden files" if self.show_hidden else "Hiding hidden files", 2)
        elif name == "start" and self.kind in LISTEN_KINDS:
            self.view, self.now_from = "now", "list"
        elif name == "start" and grid and n:
            self.open_photo([x["src"] for x in items], sel)
            self.v["slideshow"], self.v["next_t"] = True, time.monotonic() + SLIDESHOW_SECS
        elif n:
            step = {"up": -cols, "down": cols,
                    "left": -1 if grid else -page, "right": 1 if grid else page}.get(name)
            if step is not None:
                if grid or repeat or name in ("left", "right"):
                    sel = max(0, min(sel + step, n - 1))
                else:
                    sel = (sel + step) % n
                self.confirm = (None, 0.0)
            elif name == "a":
                self.open_item(items, sel)
                self.dirty = True
                return None
            self.sels[self.tab] = sel
        self.dirty = True
        return None

    def flush(self):
        """Redraw the screen if something changed (never over a video, or 'Shutting down')."""
        if not (self.active and self.dirty and self.fb) or time.monotonic() < self.halting:
            return
        if self.proc_owns_screen():
            return
        self.dirty = False
        draw = {"home": self.render_home, "keys": self.render_keys, "help": self.render_help,
                "learn": self.render_learn, "gamemenu": self.render_game_menu,
                "photo": self.render_photo, "keepres": self.render_keep_res,
                "pdf": self.render_pdf,
                "text": self.render_text, "wait": lambda: self.render_wait(
                    self.v.get("title", ""), self.v.get("status", ""))}.get(self.view)
        if draw:
            draw()
        elif self.view == "now" and self.kind in LISTEN_KINDS:
            self.render_now()
        else:
            self.render_list()
