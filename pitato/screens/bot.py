"""The Bot tab: chatting, its pictures and its voice, and Settings > Bot."""
import io
import random
import re
import shutil
import time

from ..theme import ACCENT, BG, BODY, LINE, MUTED, ROW, TEXT, WARN
from ..config import clean_name, edit_config
from ..util import pictures_dir, save_picture
from ..net import cam_address
from ..screen import aplay_device
from ..library import LIBRARY
from ..weather import place_text, wx_words
from ..cameras import read_cameras
from ..stocks import money
from ..voice import BOT_VOICES, voice_name, VOICE_SAMPLE, voices_here
from ..bot import (
    Friend, FRIEND_BUBBLE, FRIEND_CHATTER, FRIEND_FACES, FRIEND_HEAD, FRIEND_HELLO_AFTER, FRIEND_KEEP,
    FRIEND_PAGES, FRIEND_PIC_ROOM, FRIEND_SIGHT, FRIEND_TOPICS)
from ..coder import CODER_BUSY, CODER_TITLES


class BotScreen:
    """The Bot tab: chatting, its pictures and its voice, and Settings > Bot."""

    def on_bot_page(self):
        """The Bot is on screen (chatting or at work)."""
        return self.active and self.view == "list" and self.tab_type() == "friend"

    def bot_mode(self):
        """The Bot chats ("chat") or acts out your coding agent ("work"): left and right switch."""
        return "work" if self.setting("bot_mode") == "work" else "chat"

    def bot_label(self, d):
        """Top left on the Bot: chatting, or at work (left and right switch)."""
        F = self.fonts
        word = "Work" if self.bot_mode() == "work" else "Chat"
        x, y = 28, self.LIST_TOP + 16
        w = d.textlength(word, font=F["small"]) + 34
        d.rounded_rectangle((x, y, x + w, y + 26), radius=13, fill=ROW if word == "Work" else BG)
        d.ellipse((x + 11, y + 10, x + 17, y + 16), fill=ACCENT)
        d.text((x + 24, y + 13), word, font=F["small"], fill=TEXT, anchor="lm")

    # -- the bot ---------------------------------------------------------------
    def friend_files(self):
        return LIBRARY[self.tab_index("friend")]["files"]

    def on_friend_page(self):
        """The Bot is on screen, chatting."""
        return self.on_bot_page() and self.bot_mode() == "chat"

    def friend_changed(self):
        """It said something, or started or stopped thinking (from its thread)."""
        if len(self.friend.log) != self.friend_seen:
            self.friend_seen = len(self.friend.log)
            self.friend_scroll = 0                    # back to the newest
        if self.on_friend_page() or (self.active and self.view == "list" and self.tab_type() == "settings"
                                     and self.set_page in FRIEND_PAGES):
            self.dirty = True

    def friend_opened(self):
        fr = self.friend
        self.friend_opened_at = time.time()
        self.friend_scroll = 0
        if fr.ready() and self.bot_voice() and self.bot_speaks() and not self.proc:
            self.voice.warm(self.bot_voice())          # (a voice takes a few seconds to load)
        if fr.ready() and not fr.busy and time.time() - fr.last_said() > FRIEND_HELLO_AFTER:
            fr.remark("hello")

    # its voice
    def bot_voice(self):
        """The voice picked in Settings > Bot ("" for none)."""
        return clean_name(self.friend.conf.get("voice"), 80)

    def bot_speaks(self):
        """Its replies said out loud (when it has a voice)."""
        return (self.friend.conf.get("speak") or "on").strip().lower() not in ("off", "no", "0", "false")

    def say_aloud(self, text=None):
        """A reply said out loud: the last one when none is given (not over something playing, which
        has the sound, and the memory). (True, "") or (False, why not)."""
        if self.proc:
            return False, "Not while something's playing"
        if self.coder.talking():
            return False, "Not while your coding agent is talking"
        if text is None:
            last = next((x for x in reversed(self.friend.log)
                         if x["who"] == "friend" and x.get("kind") != "error"), None)
            if not last:
                return False, "It hasn't said anything yet"
            text = last["text"]
        self.dirty = True
        return self.voice.say(text, self.bot_voice(), aplay_device(self.setting("sound")), self.volume)

    def bot_replied(self, text):
        """It answered (on its own thread): out loud too, when that's set and nothing is playing."""
        if self.bot_voice() and self.bot_speaks() and not self.proc:
            self.say_aloud(text)

    def voice_ready(self, vid):
        """A voice arrived (on its download's thread): the main loop puts it to use."""
        self.voice_arrived = vid
        self.dirty = True

    def voice_use(self, vid):
        """The voice in bot.txt, and a word in it, so you hear how it sounds."""
        self.voice_arrived = None
        if vid != self.voice_want:
            return
        self.voice_want = None
        if self.friend_set(voice=vid):
            self.toast(f"{voice_name(vid)} is ready", 3)
            self.say_aloud(VOICE_SAMPLE)

    def voice_pick(self, vid):
        """A voice chosen (in Settings, or on the web page): used at once if it's on the Pi, fetched
        first if it isn't. (True, what's happening) or (False, why not)."""
        if not vid:
            self.voice_want = None
            self.voice.stop(unload=True)
            return (True, "No voice") if self.friend_set(voice="") else (False, "Couldn't save static/bot.txt")
        if vid in voices_here() and self.voice.have_piper():
            self.voice_want = None
            if not self.friend_set(voice=vid):
                return False, "Couldn't save static/bot.txt"
            self.say_aloud(VOICE_SAMPLE)
            return True, f"Using {voice_name(vid)}"
        if vid not in [i for i, _, _ in BOT_VOICES] and vid not in voices_here():
            return False, "There's no such voice"
        if not self.voice.supported():
            return False, "Piper doesn't run on this Pi"
        job = self.voice.job
        if job:
            return False, f"Still getting {job['what']}"
        self.voice_want = vid
        self.voice.get(vid)
        return True, f"Getting {voice_name(vid)}…"

    def friend_topic(self):
        """Something to talk about: mostly the weather and the time, the stocks and coins now and then, and
        what it sees, when it has a camera (and its model hasn't turned out not to see)."""
        fr = self.friend
        topic = random.choice(FRIEND_TOPICS + (["sight"] * FRIEND_SIGHT if fr.sees() and self.friend_camera() else []))
        if topic == "weather" and not self.weather.data:
            topic = "time"
        if topic == "markets" and not (any((self.crypto.quotes.get(c["id"]) or {}).get("d") for c in self.crypto.coins)
                                       or any((self.stocks.quotes.get(s) or {}).get("d") for s in self.stocks.symbols())):
            topic = "anything"
        if topic == "playing" and not (self.proc and self.cur):
            topic = "anything"
        return topic

    def friend_facts(self):
        """What's true right now, for it to talk about."""
        t = time.localtime()
        lines = [f"Time: {time.strftime('%A', t)} {self.clock_text(t)}"]
        loc = self.setting("location")
        if loc:
            lines.append(f"Where you are: {place_text(loc)}")
        w = self.weather.data
        try:
            if w and w.get("temp") is not None:
                u = w.get("units") or "F"
                lines.append(f"Weather now: {round(w['temp'])}°{u}, {wx_words(w.get('code'))[0].lower()}, "
                             f"feels like {round(w.get('feels') if w.get('feels') is not None else w['temp'])}°, "
                             f"humidity {w.get('humidity')}%, wind {round(w.get('wind') or 0)}")
                days = w.get("days") or []
                if days and days[0].get("hi") is not None:
                    d0 = days[0]
                    lines.append(f"Today: high {round(d0['hi'])}°, low {round(d0['lo'])}°, {d0.get('rain') or 0}% "
                                 f"chance of rain, sunrise {d0.get('sunrise')}, sunset {d0.get('sunset')}")
                    ahead = [f"{time.strftime('%a', time.strptime(x['date'], '%Y-%m-%d'))} {round(x['hi'])}/"
                             f"{round(x['lo'])}° {wx_words(x.get('code'))[0].lower()}" for x in days[1:4]]
                    if ahead:
                        lines.append("Next few days: " + "; ".join(ahead))
        except (KeyError, TypeError, ValueError):
            pass
        stocks = []
        for sym in self.stocks.symbols()[:3]:
            q = (self.stocks.quotes.get(sym) or {}).get("d") or {}
            if q.get("price") is not None:
                ch = q.get("change_1d")
                stocks.append(f"{q.get('name') or sym} ({sym}) {money(q['price'], q.get('currency') or 'USD', q.get('kind') or '')}"
                              + (f" ({ch:+.1f}% today)" if ch is not None else ""))
        if stocks:
            lines.append("Stocks: " + ", ".join(stocks))
        coins = []
        for c in self.crypto.coins[:3]:
            q = (self.crypto.quotes.get(c["id"]) or {}).get("d") or {}
            if q.get("price") is not None:
                ch = q.get("change_24h")
                coins.append(f"{q.get('symbol') or c['symbol']} ${q['price']:,.2f}"
                             + (f" ({ch:+.1f}% in a day)" if ch is not None else ""))
        if coins:
            lines.append("Coins: " + ", ".join(coins))
        if self.proc and self.cur:
            title = self.cur.get("title") or ""
            song = self.meta.get("song") if self.kind == "radio" else ""
            lines.append(f"Playing now: {title}" + (f" ({song})" if song else ""))
        return lines

    def friend_camera(self, text=""):
        """The camera the bot looks through: one named in what you said ("take a picture with the
        garage camera"), the one on the Camera tab, or the first of yours. "" when there's none."""
        cam = self.camera
        cams = cam.cams or read_cameras(LIBRARY[self.tab_index("camera")]["files"])
        low = (text or "").lower()
        if low:
            for c in cams:
                name = (c.get("name") or cam.name_of(c["addr"])).lower()
                if len(name) >= 3 and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", low):
                    return c["addr"]
        return cam.addr or (cams[0]["addr"] if cams else "")

    def friend_look(self, text=""):
        """A picture from your camera, for its model to look at: (its JPEG, the camera) or (None, why not)."""
        cam = self.camera
        addr = self.friend_camera(text)
        if not addr:
            return None, "there's no camera set up"
        got = cam.snapshot(addr, max_age=2)
        if not got:
            return None, f"the camera {cam.name_of(addr)} didn't answer"
        return cam.turned_file(addr, got[0], got[2]), cam.name_of(addr)

    def friend_snap(self, text=""):
        """A picture taken with your camera because you asked the bot: kept in ~/Pictures, as one taken
        on the Camera tab is. (Where it is, its bytes, the camera); ValueError: why not."""
        from PIL import Image
        addr = self.friend_camera(text)
        if not addr:
            raise ValueError("there's no camera. Add one on the Camera tab")
        data = self.camera.photo_of(addr)
        try:
            fmt = (Image.open(io.BytesIO(data)).format or "").lower()
        except Exception:
            raise ValueError("that wasn't a picture")
        try:
            if shutil.disk_usage(pictures_dir()).free < len(data) + FRIEND_PIC_ROOM:
                raise ValueError("there's no room left for it on the Pi")
            path = save_picture(data, ".png" if fmt == "png" else ".jpg")
        except OSError as e:
            raise ValueError(f"couldn't save it ({e.strerror or e})")
        self.last_shot = path
        return path, data, self.camera.name_of(addr)

    def friend_options(self):
        """The Bot page's X menu: (what it says, what it does)."""
        opts = [("Send a picture from Photos", "send")]
        if self.friend_camera():
            opts.append(("Take a picture", "snap"))
        opts.append(("Set up your bot", "setup"))
        opts.append(("Press A again to clear it" if self.confirm[0] == "friendclear" else "Clear the conversation",
                     "clear"))
        return opts

    def friend_pick(self):
        """Photos, to pick a picture for the bot: A sends it, B goes back."""
        if self.friend.busy:
            self.toast("Still thinking about the last one", 2)
            return
        pi = self.tab_index("photos")
        self.load_tab(pi)
        if not self.tab_items(pi):
            self.toast("No pictures in Photos yet", 3)
            return
        self.picking, self.tab = "bot", pi
        self.toast("Pick a picture for your bot", 3)

    def friend_pic(self, pid):
        """A picture in the conversation, as the Bot page shows it: (it, its rounded corners), kept."""
        if not pid:
            return None
        have = self.friend_pics.get(pid)
        if have is None:
            have = False
            data = Friend.picture_bytes(pid)
            if data:
                try:
                    from PIL import Image, ImageDraw
                    im = Image.open(io.BytesIO(data))
                    im.draft("RGB", FRIEND_BUBBLE)
                    im = im.convert("RGB")
                    im.thumbnail(FRIEND_BUBBLE)
                    mask = Image.new("L", im.size, 0)
                    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=9, fill=255)
                    have = (im, mask)
                except Exception:
                    have = False
            if len(self.friend_pics) > FRIEND_KEEP + 10:     # only those still in the conversation
                live = {x.get("pic") for x in list(self.friend.log)}
                self.friend_pics = {k: v for k, v in self.friend_pics.items() if k in live}
            self.friend_pics[pid] = have
        return have or None

    def press_friend(self, name, repeat):
        fr = self.friend
        if self.friend_more is not None:               # the X menu
            opts = self.friend_options()
            menu = self.friend_more
            if name in ("up", "down"):
                menu["sel"] = (menu["sel"] + (1 if name == "down" else -1)) % len(opts)
                self.confirm = (None, 0.0)
            elif name == "a" and not repeat:
                what = opts[menu["sel"] % len(opts)][1]
                if what == "clear" and self.confirm[0] != "friendclear":
                    self.confirm = ("friendclear", time.monotonic() + 4)      # A again to clear it
                else:
                    self.friend_more = None
                    self.confirm = (None, 0.0)
                    if what == "clear":
                        fr.clear()
                        self.toast("Conversation cleared", 2)
                    elif what == "send":
                        self.friend_pick()
                    elif what == "snap":
                        self.friend_send("Take a picture")
                    elif what == "setup":
                        self.friend_setup()
            elif name in ("b", "x") and not repeat:
                self.friend_more = None
                self.confirm = (None, 0.0)
            self.dirty = True
            return None
        if name in ("l", "r", "b"):
            return "pass"
        if repeat and name not in ("up", "down"):
            return None
        if name == "start" or (name == "a" and not fr.ready()):
            self.friend_setup()
        elif not fr.ready():
            pass
        elif name == "select":
            if self.voice.speaking:
                self.voice.stop()
            else:
                ok, why = self.say_aloud()
                if not ok:
                    self.toast(why, 3)
        elif name == "a":
            if fr.busy:
                self.toast("Still thinking about the last one", 2)
            else:
                self.open_keyboard("Say something to your bot", "", self.friend_send, limit=200)
        elif name == "y":
            if not fr.remark(self.friend_topic()):
                self.toast("Still thinking about the last one", 2)
        elif name == "x" and not repeat:
            self.friend_more = {"sel": 0}
            self.confirm = (None, 0.0)
        elif name in ("up", "down"):
            self.friend_scroll = max(0, self.friend_scroll + (72 if name == "up" else -72))
        self.dirty = True
        return None

    def press_bot(self, name, repeat):
        """The Bot: left and right switch it between chatting and work (not while its menu or a card is
        open); the rest is up to the one on screen."""
        work = self.bot_mode() == "work"
        if name in ("left", "right") and self.friend_more is None and not self.coder_help:
            if not repeat:
                self.bot_set_mode("chat" if work else "work")
            return None
        return self.press_coder(name, repeat) if work else self.press_friend(name, repeat)

    def bot_set_mode(self, mode):
        """Chat or work, kept for next time."""
        self.friend_more, self.coder_help = None, False
        self.confirm = (None, 0.0)
        self.set_setting("bot_mode", mode)
        if mode == "chat" and self.on_friend_page():
            self.friend_opened()
        self.dirty = True

    def bot_open(self, mode):
        """The Bot on the screen, chatting or at work (the web page)."""
        self.set_setting("bot_mode", mode)
        self.web_tab("Bot")

    def bot_work_line(self):
        """While it chats: a word on what your coding agent is up to, (words, colour), or None."""
        s = self.coder.snapshot(time.monotonic())
        a = s["anim"]
        if not s["heard"] or s["asleep"]:
            return None
        if a in CODER_BUSY:
            return f"Your agent is {CODER_TITLES[a].lower()}", ACCENT
        if a == "attention":
            return "Your agent needs you", WARN
        if a == "error":
            return CODER_TITLES[a], WARN
        if s["done"] and time.time() - s["done"][0] < 600:
            return "Your agent is done", MUTED
        return None

    def friend_send(self, text, picture=None):
        if not self.friend.say(text, picture=picture):
            self.toast("Still thinking about the last one", 2)
        self.friend_scroll = 0

    def friend_setup(self):
        """Settings > Bot."""
        self.tab = self.tab_index("settings")
        self.load_tab(self.tab)
        self.set_page, self.set_sel = "friend", 0
        self.friend.load(self.friend_files())
        if self.friend.server and self.friend.models_at != self.friend.server:
            self.friend.fetch_models()
        self.dirty = True

    def friend_set(self, **updates):
        """Settings > Bot into bot.txt (which starts from friend.txt, its earlier name)."""
        try:
            edit_config("bot.txt", {k: " ".join(str(v).split()) for k, v in updates.items()}, head=FRIEND_HEAD,
                        was="friend.txt")
        except OSError as ex:
            self.toast(f"Couldn't save it ({ex.strerror or ex})", 4)
            return False
        self.friend.load(self.friend_files())
        self.dirty = True
        return True

    def friend_set_server(self, text):
        text = text.strip()
        if text and not cam_address(text):
            self.toast("That isn't an address. Try 192.168.1.20", 4)
            return
        if self.friend_set(server=text) and text:
            self.friend.fetch_models()

    def friend_summary(self):
        fr = self.friend
        fr.load(self.friend_files())
        return fr.model if fr.ready() else ("Pick a model" if fr.server else "Not set up")

    def friend_value(self, key):
        fr = self.friend
        if key == "f_voice":
            job = self.voice.job
            if job and job["id"] == self.voice_want:
                return f"Getting it… {job['pct']}%"
            if not self.voice.supported():
                return "Not on this Pi"
            return voice_name(self.bot_voice()) if self.bot_voice() else "None"
        if key == "f_speak":
            return "On" if self.bot_speaks() else "Off"
        return {"f_server": fr.server or "Not set", "f_model": fr.model or "Pick one",
                "f_name": fr.name or "Not set", "f_chatter": fr.chatter_text()}.get(key, "")

    def press_friend_settings(self, name, repeat, key, extra):
        fr = self.friend
        if repeat:
            return None
        page = self.set_page
        if name == "b":
            if page == "friend":
                self.set_page, self.set_sel = "root", self.settings_root_index("friend")
            else:
                self.set_page, self.set_sel = "friend", {"f_models": 1, "f_voices": 4}.get(page, 0)
            self.confirm = (None, 0.0)
        elif page == "f_voices":
            self.press_voices(name, key, extra)
        elif name == "x":
            fr.fetch_models()
        elif page == "friend":
            if name == "a" and key == "f_server":
                self.open_keyboard("Computer with Ollama (its address)", fr.server, self.friend_set_server,
                                   row=0, limit=120, empty=True)
            elif name == "a" and key == "f_name":
                self.open_keyboard("What should it call you?", fr.name,
                                   lambda t: self.friend_set(name=t), limit=40, empty=True)
            elif name == "a" and key == "f_model":
                if not fr.server:
                    self.toast("Set the computer with Ollama first", 3)
                else:
                    self.set_page = "f_models"
                    rows = self.settings_rows()
                    self.set_sel = next((i for i, r in enumerate(rows) if r[2] == fr.model), 0)
                    if fr.models_at != fr.server or not fr.models:
                        fr.fetch_models()
            elif key == "f_chatter" and name in ("left", "right", "a"):
                labels = [t for t, _ in FRIEND_CHATTER]
                cur = fr.chatter_text()
                i = labels.index(cur) if cur in labels else 0
                new = FRIEND_CHATTER[(i + (-1 if name == "left" else 1)) % len(FRIEND_CHATTER)]
                self.friend_set(chatter=new[1])
            elif name == "a" and key == "f_voice":
                if not self.voice.supported():
                    self.toast("Piper doesn't run on this Pi", 3)
                else:
                    self.set_page = "f_voices"
                    rows = self.settings_rows()
                    want = self.voice_want or self.bot_voice()
                    self.set_sel = next((i for i, r in enumerate(rows) if r[2] == want), 0)
            elif key == "f_speak" and name in ("left", "right", "a"):
                if not self.bot_voice():
                    self.toast("Pick a voice first", 3)
                else:
                    self.friend_set(speak="off" if self.bot_speaks() else "on")
                    if not self.bot_speaks():
                        self.voice.stop()
        elif name == "a" and key == "f_pick":
            self.friend_set(model=extra)
            self.toast(f"Using {extra}", 2)
            self.set_page, self.set_sel = "friend", 1
        self.dirty = True
        return None

    def press_voices(self, name, key, extra):
        """Settings > Bot > Voice: A uses one (fetching it the first time), X twice takes one off."""
        if name == "a":
            ok, what = self.voice_pick(extra if key == "v_pick" else "")
            self.toast(what, 3)
            self.confirm = (None, 0.0)
        elif name == "x" and key == "v_pick" and extra in voices_here():
            if self.confirm[0] == "voicerm:" + extra:
                self.confirm = (None, 0.0)
                if extra == self.bot_voice():
                    self.friend_set(voice="")
                self.voice.remove(extra)
                self.toast(f"Took {voice_name(extra)} off the Pi", 3)
            else:
                self.confirm = ("voicerm:" + extra, time.monotonic() + 4)
                self.toast(f"Press X again to take {voice_name(extra)} off the Pi", 4)

    def render_friend(self):
        from PIL import Image, ImageDraw
        F = self.fonts
        fr = self.friend
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        top, bottom = self.LIST_TOP + 4, H - self.FOOTER - 10
        # its face, in a card on the left
        cx0, cx1 = 16, 196
        d.rounded_rectangle((cx0, top, cx1, bottom), radius=18, fill=ROW)
        face, mood = fr.face() if fr.ready() else (FRIEND_FACES["sleepy"], "sleepy")
        mid = (top + bottom) / 2 - 16
        d.text(((cx0 + cx1) / 2, mid), face, font=F["face"], fill=TEXT, anchor="mm")
        speaking = self.voice.speaking
        status = (fr.doing or "Thinking…") if fr.busy else "Speaking…" if speaking else \
            self.fit(d, fr.model, F["small"], cx1 - cx0 - 24) if fr.ready() else "Not set up"
        d.text(((cx0 + cx1) / 2, mid + 50), status, font=F["small"], fill=ACCENT if fr.busy or speaking else MUTED,
               anchor="mm")
        self.bot_label(d)
        work = self.friend_work_shown = self.bot_work_line()
        if work:                                      # (your coding agent: left or right shows it)
            d.text(((cx0 + cx1) / 2, bottom - 24), self.fit(d, work[0], F["small"], cx1 - cx0 - 20), font=F["small"],
                   fill=work[1], anchor="mm")

        # the conversation on the right, the newest at the bottom (above a notice while one is up)
        x0, x1 = cx1 + 14, W - 16
        pw, ph = x1 - x0, bottom - top - (44 if self.msg else 0)
        if not fr.ready():
            lines = [("Set up your bot", F["big"], TEXT), ("", F["small"], MUTED),
                     ("It talks through Ollama on another", F["small"], BODY),
                     ("computer on your network.", F["small"], BODY), ("", F["small"], MUTED),
                     ("Press A to set it up.", F["small"], MUTED)]
            y = top + ph / 2 - 60
            for text, font, colour in lines:
                d.text((x0 + pw / 2, y), text, font=font, fill=colour, anchor="mm")
                y += 26 if font is F["big"] else 22
        else:
            panel = Image.new("RGB", (pw, ph), BG)
            pd = ImageDraw.Draw(panel)
            font = F["chat"]
            lh = 24
            maxw = int(pw * 0.86)
            mine = tuple(int(a * 0.32 + b * 0.68) for a, b in zip(ACCENT, ROW))
            bubbles = []
            for x in list(fr.log):
                pic = self.friend_pic(x.get("pic"))
                lines = self.wrap(pd, x["text"], font, maxw - 28, lines=40) if x.get("text") else []
                w = max([pd.textlength(ln, font=font) + 28 for ln in lines] + ([pic[0].width + 16] if pic else [40]))
                h = 16 + len(lines) * lh + ((pic[0].height + (8 if lines else 0)) if pic else 0)
                bubbles.append((x["who"], x.get("kind"), lines, int(w), h, pic))
            if fr.busy:
                bubbles.append(("friend", "typing", [], 70, 40, None))
            total = sum(b[4] + 10 for b in bubbles)
            self.friend_scroll = max(0, min(self.friend_scroll, total - ph))
            y = ph + self.friend_scroll
            for who, kind, lines, w, h, pic in reversed(bubbles):
                y -= h
                if y + h < 0:
                    break
                if y < ph:
                    bx0 = pw - w if who == "you" else 0
                    pd.rounded_rectangle((bx0, y, bx0 + w, y + h), radius=14,
                                         fill=mine if who == "you" else ROW)
                    if kind == "typing":
                        for k in range(3):
                            pd.ellipse((bx0 + 18 + k * 14, y + h / 2 - 4, bx0 + 26 + k * 14, y + h / 2 + 4),
                                       fill=MUTED)
                    ty = y + 8
                    if pic:                            # a picture: sent, taken, or what it looked at
                        panel.paste(pic[0], (bx0 + 8, y + 8), pic[1])
                        ty += pic[0].height + 8
                    for k, ln in enumerate(lines):
                        pd.text((bx0 + 14, ty + k * lh + lh / 2), ln, font=font,
                                fill=WARN if kind == "error" else TEXT, anchor="lm")
                y -= 10
            if not bubbles:
                pd.text((pw / 2, ph / 2 - 14), "Say hello", font=F["big"], fill=TEXT, anchor="mm")
                pd.text((pw / 2, ph / 2 + 18), "A to talk, or Y and it says something", font=F["small"],
                        fill=MUTED, anchor="mm")
            img.paste(panel, (x0, top))
            if self.friend_scroll:
                d.text((x0 + pw / 2, top + ph - 4), "▼", font=F["small"], fill=MUTED, anchor="mb")
        if fr.ready() and self.friend_more is not None:   # the X menu, over the conversation
            opts = self.friend_options()
            sel = self.friend_more["sel"] % len(opts)
            mw, rh = 320, 44
            mx0, my0 = x0 + (pw - mw) / 2, top + 30
            d.rounded_rectangle((mx0 - 2, my0 - 2, mx0 + mw + 2, my0 + 44 + len(opts) * rh + 12), radius=14, fill=LINE)
            d.rounded_rectangle((mx0, my0, mx0 + mw, my0 + 42 + len(opts) * rh + 10), radius=13, fill=BG)
            d.text((mx0 + 20, my0 + 22), "Your bot", font=F["small"], fill=MUTED, anchor="lm")
            for k, (label, what) in enumerate(opts):
                ry = my0 + 42 + k * rh
                if k == sel:
                    d.rounded_rectangle((mx0 + 8, ry, mx0 + mw - 8, ry + rh - 4), radius=10, fill=ROW)
                colour = (WARN if what == "clear" and self.confirm[0] == "friendclear" else TEXT) if k == sel else BODY
                d.text((mx0 + 22, ry + (rh - 4) / 2), self.fit(d, label, F["row"], mw - 44), font=F["row"],
                       fill=colour, anchor="lm")
            hints = [("▲▼", "Choose"), ("A", "OK"), ("B", "Close")]
        elif fr.ready():
            hints = [("◀▶", "Work"), ("A", "Talk"), ("Y", "Say something"), ("X", "More")]
            hints += [("SELECT", "Stop" if speaking else "Speak")] if self.bot_voice() else [("▲▼", "Scroll")]
        else:
            hints = [("◀▶", "Work"), ("A", "Set up"), ("L R", "Tabs"), ("B", "Home")]
        self.footer(d, hints)
        self.fb.show(img)
