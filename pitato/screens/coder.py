"""The Bot at work: your coding agent acted out, prompts sent to it, and its requests to use a tool answered."""
import socket
import time

from ..theme import ACCENT, BG, BODY, LINE, MUTED, ROW, TEXT
from ..config import read_config, settings_glob, WEB_PORT
from ..system import run_out
from ..screen import aplay_device
from ..library import VOLUME_STEP
from ..coder import (
    ASK_ABOUT_MAX, ASK_ID, ASK_PREVIEW_MAX, ask_text, ASK_TOOL_MAX, CO_DIRTY, co_span, CO_TOP, CODER_BUSY,
    CODER_CHANNEL, coder_desk, coder_draw, coder_extras, CODER_POSES, CODER_SAY_AS, CODER_TITLES, coder_under,
    coder_wav, PROMPT_MAX)


class CoderScreen:
    """The Bot at work: your coding agent acted out, and prompts sent to it."""

    def on_coder_page(self):
        """The Bot is on screen at work."""
        return self.on_bot_page() and self.bot_mode() == "work"

    # -- the Bot at work: your coding agent, acted out ----------------------------------------
    def coder_changed(self):
        if self.on_coder_page():
            self.dirty = True
        elif self.on_friend_page() and self.bot_work_line() != self.friend_work_shown:
            self.dirty = True                         # (the chat's word about your agent)

    def coder_may_sound(self):
        """Where the Bot's sounds at work go and how loud, or None to keep quiet: its sounds are off, or the
        speaker is busy (something playing, the bot talking, the Pi shutting down). (Any thread.)"""
        if self.setting("coder_sound") == "Off" or self.proc or self.game is not None or self.voice.speaking \
                or time.monotonic() < self.halting:
            return None
        return aplay_device(self.setting("sound")), self.volume

    def coder_news(self, name):
        """It's done, or it needs you, while you're elsewhere in media mode: a word about it."""
        if self.active and not self.on_coder_page() and not self.proc_owns_screen():
            self.toast("Your coding agent is done" if name == "done" else "Your coding agent needs you", 4)

    def coder_status(self, s):
        """The words on its desk: what it's doing, and since when."""
        a, now = s["anim"], time.time()
        if not s["heard"] and not self.setting("coder_seen"):
            return "Waiting for your coding agent", "START shows how to connect it"
        if s["asleep"] or (a == "sleep" and s["t"] > 1.2):
            return "Asleep", ""
        if a in CODER_BUSY:
            busy = now - s["work_from"] if s["work_from"] else 0
            return CODER_TITLES[a], f"for {co_span(busy)}" if busy >= 10 else ""
        if a in ("done", "rest") and s["done"]:
            when, took = s["done"]
            return "Done", f"at {self.clock_text(time.localtime(when))}" + (f", after {co_span(took)}" if took >= 60 else "")
        if a == "attention":
            return CODER_TITLES[a], f"since {self.clock_text(time.localtime(now - s['t']))}"
        if a == "error":
            return CODER_TITLES[a], f"at {self.clock_text(time.localtime(now - s['t']))}"
        return CODER_TITLES.get(a, "Ready"), ""

    def coder_hints(self, s):
        if self.coder_help:
            return [("B", "Close")]
        if self.coder_ask_shown() is not None:
            return [("A", "Allow"), ("B", "Deny"), ("X", "Later")]
        y = ("Y", "OK") if s["anim"] in ("attention", "error") else ("Y", "Ring")
        return [("◀▶", "Chat"), ("A", "Prompt"), y, ("X", "Sound", self.setting("coder_sound") != "Off"),
                ("START", "Connect")]

    def prompt_open(self):
        """A on the Bot at work: a prompt for your coding agent (the one you left, if you backed out), once
        it's listening for them."""
        if not self.prompts.listening():
            self.toast("Your coding agent isn't listening for prompts. START shows how", 4)
            return
        kb = self.open_keyboard("A prompt for your coding agent", self.prompt_draft,
                                lambda text: self.prompt_done(text, kb), empty=True, limit=PROMPT_MAX, local=True,
                                cancel=self.prompt_keep)

    def prompt_keep(self, text):
        self.prompt_draft = text

    def prompt_done(self, text, kb):
        """Your prompt, typed: off to your agent. Only from the Pi's own buttons and keyboard: the web page's
        remote can work the screen, but it can't hand your agent something to do."""
        self.prompt_draft = text
        if not text:
            return
        if kb.get("remote"):
            self.toast("Prompts are typed on the Pi itself, not with the web page's remote", 4)
        elif not self.prompts.listening():
            self.toast("Your coding agent isn't listening for prompts. It's kept for you", 4)
        else:
            self.prompts.put(text)
            self.prompt_draft = ""
            self.toast("Sending your prompt", 3)

    def prompt_taken(self, prompt):
        """Your agent got a prompt you sent. (The control server's thread.)"""
        if self.active and not self.proc_owns_screen():
            self.toast("Your coding agent has your prompt", 3)
        heard = self.coder.heard
        if heard and time.time() - heard < 12 * 3600:   # (its hooks will say what it does next)
            self.coder.ask("thinking", agent=False)

    def prompt_expired(self):
        """Prompts your agent didn't take in time: yours to send again."""
        old = self.prompts.expire()
        if old:
            self.prompt_draft = " ".join([p["text"] for p in old] + [self.prompt_draft]).strip()
            if self.active and not self.proc_owns_screen():
                self.toast("Your coding agent didn't take your prompt. It's kept for you", 5)

    def coder_addresses(self):
        """For connecting an agent: the web page by name and by number, and whether it has a password."""
        ips = [x for x in run_out(["hostname", "-I"]).split() if ":" not in x]
        locked = bool(read_config([settings_glob("webui.txt")]).get("password"))
        return (f"http://{socket.gethostname()}.local:{WEB_PORT}",
                f"http://{ips[0]}:{WEB_PORT}" if ips else "", locked)

    def press_coder(self, name, repeat):
        """The Bot at work: A types a prompt for your coding agent, Y rings its bell (or says you've seen
        what it wanted), X turns its sounds on or off, up and down the volume, START shows how to connect
        an agent. While your agent asks to use a tool: A allows it, B denies it, X leaves it to the computer."""
        co = self.coder
        if self.coder_help:
            if name in ("l", "r"):
                return "pass"
            if name in ("a", "b", "start") and not repeat:
                self.coder_help = False
                self.dirty = True
            return None
        ask = self.coder_ask_shown()
        if ask is not None and name in ("a", "b", "x"):
            if not repeat:
                self.coder_answer(ask, name)
            return None
        if name in ("up", "down"):
            self.set_volume(VOLUME_STEP if name == "up" else -VOLUME_STEP)
            self.toast(f"Volume {self.volume}", 2)
            return None
        if repeat:
            return None
        if name == "a":
            self.prompt_open()
        elif name == "y":
            co.ask("rest" if co.current() in ("attention", "error") else "done", agent=False)
        elif name == "x":
            on = self.setting("coder_sound") == "Off"
            self.set_setting("coder_sound", "On" if on else "Off")
            self.toast("Its sounds are on" if on else "Its sounds are off", 2)
        elif name == "start":
            self.coder_help, self.coder_where = True, None
        else:
            return "pass"
        self.dirty = True
        return None

    # -- your agent asks to use a tool (Claude Code's permission prompt, through the channel) ---------------------
    def coder_ask_shown(self):
        """Your agent's oldest request to use a tool that's waiting for your answer here (not left for the
        computer), or None."""
        return next((a for a in self.prompts.pending() if not a["hidden"]), None)

    def coder_answer(self, ask, name):
        """A allows what your agent asked, B denies it, X leaves it to the computer. Only from the Pi's own buttons
        and keyboard: the web page's remote can work the screen, but it can't let your agent do something."""
        if name == "x":
            self.prompts.hide(ask["id"])
            self.toast("Left for the computer to answer", 3)
        elif self.web_guard:                           # (or another of your Pietatos controlling this one: the same)
            self.toast("Answer it on the Pi itself, not from another Pietato" if self.web_guard == "pilot"
                       else "Answer it on the Pi itself, not with the web page's remote", 4)
        elif self.prompts.answer(ask["id"], "allow" if name == "a" else "deny"):
            self.toast(f"Allowed: {ask['tool']}" if name == "a" else f"Denied: {ask['tool']}", 3)
            self.coder.ask("thinking" if name == "a" else "shrug", agent=False)
        self.dirty = True

    def prompt_asked(self, ask):
        """Your agent asks to use a tool: it looks up from its desk, and a word about it if you're elsewhere. (The
        control server's thread.)"""
        self.coder.ask("attention")
        if self.active and not self.on_coder_page() and not self.proc_owns_screen():
            self.toast(f"Your coding agent asks to use {ask['tool']}: answer on the Bot at work", 5)
        self.dirty = True

    def coder_ask_card(self, img, ask):
        """Your agent's request, over its desk: what it wants to use, its words about it, the details (a command,
        a file), and that the computer can answer it too."""
        from ..fine import ImageDraw
        F, W, H = self.fonts, self.fb.w, self.fb.h
        d = ImageDraw.Draw(img)
        x0, x1 = 24, W - 24
        inner = x1 - x0 - 48
        about = self.wrap(d, ask["about"], F["small"], inner, lines=2) if ask["about"] else []
        detail = self.wrap(d, ask["preview"], F["mono_s"], inner - 16, lines=2) if ask["preview"] else []
        h = 26 + 30 + 24 * len(about) + (12 + 26 * len(detail) + 8 if detail else 0) + 30 + 6
        y1 = H - (0 if self.full_app() else self.FOOTER) - 10
        y0 = max(self.HEADER + 8, y1 - h)
        d.rounded_rectangle((x0, y0, x1, y1), radius=16, fill=ROW, outline=LINE)
        x, y = x0 + 24, y0 + 30
        d.text((x, y), self.fit(d, f"Allow {ask['tool']}?", F["head"], inner), font=F["head"], fill=TEXT, anchor="lm")
        y += 30
        for line in about:
            d.text((x, y), line, font=F["small"], fill=BODY, anchor="lm")
            y += 24
        if detail:
            y += 4
            d.rounded_rectangle((x - 8, y - 14, x1 - 16, y - 14 + 26 * len(detail) + 4), radius=8, fill=BG)
            for line in detail:
                d.text((x, y), line, font=F["mono_s"], fill=TEXT, anchor="lm")
                y += 26
            y += 8
        d.text((x, y + 4), "Or answer it at the computer", font=F["small"], fill=MUTED, anchor="lm")

    def web_coder_ask(self, cmd):
        """POST /coder/ask: your agent asks to use a tool (Claude Code's permission prompt, which coder_hooks.py's
        channel passes on). It's shown on the Bot at work for you to answer. (The control server's thread.)"""
        rid = cmd.get("request_id")
        if not isinstance(rid, str) or not ASK_ID.fullmatch(rid):
            return {"ok": False, "error": "request_id is its five letters"}
        words = [cmd.get(k) for k in ("tool_name", "description", "input_preview")]
        if not all(w is None or isinstance(w, str) for w in words):
            return {"ok": False, "error": "tool_name, description and input_preview are words"}
        tool, about, preview = words
        new = self.prompts.ask(rid, ask_text(tool, ASK_TOOL_MAX) or "a tool", ask_text(about, ASK_ABOUT_MAX),
                               ask_text(preview, ASK_PREVIEW_MAX))
        return {"ok": True, "new": new}

    def coder_card(self, img):
        """START on the Bot at work: how to connect an agent to it, and to send it prompts from here."""
        from ..fine import ImageDraw
        F, W = self.fonts, self.fb.w
        d = ImageDraw.Draw(img)
        if self.coder_where is None:
            self.coder_where = self.coder_addresses()
        by_name, by_number, locked = self.coder_where
        host = by_name.split("//")[1].rsplit(":", 1)[0]
        setup = [f"curl -O {by_name}/coder_hooks.py", f"python3 coder_hooks.py {host}"]
        start = [f"claude --dangerously-load-development-channels server:{CODER_CHANNEL}"]
        notes = []
        if by_number:
            notes.append(f"(or use {by_number.split('//')[1].rsplit(':', 1)[0]} for {host})")
        if locked:
            notes.append("Your web page has a password: add --password and it.")
        x0, x1 = 24, W - 24
        h = 30 + 32 + 30 + 34 * len(setup) + 24 * len(notes) + 10 + 30 + 34 * len(start) + 6 + 24 + 4
        y0 = max(self.HEADER + 6, (self.HEADER + CO_TOP + max(0, self.fb.h - 480)) / 2 - h / 2)
        d.rounded_rectangle((x0, y0, x1, y0 + h), radius=16, fill=ROW)
        x, y = x0 + 24, y0 + 28
        d.text((x, y), "Connect Claude Code", font=F["head"], fill=TEXT, anchor="lm")
        y += 32
        cmds = setup + start
        font = F["mono_s"] if max(d.textlength(c, font=F["mono_s"]) for c in cmds) <= x1 - x0 - 56 else F["co_mono_xs"]

        def block(lines, y):
            d.rounded_rectangle((x0 + 14, y - 17, x1 - 14, y - 17 + 34 * len(lines)), radius=9, fill=BG)
            for c in lines:
                d.text((x + 4, y), self.fit(d, c, font, x1 - x0 - 56), font=font, fill=TEXT, anchor="lm")
                y += 34
            return y
        d.text((x, y), "On the computer it runs on:", font=F["small"], fill=BODY, anchor="lm")
        y = block(setup, y + 30) - 4
        for note in notes:
            d.text((x + 4, y), note, font=F["small"], fill=MUTED, anchor="lm")
            y += 24
        y += 10
        d.text((x, y), "For prompts from here (A), start Claude Code with:", font=F["small"], fill=BODY, anchor="lm")
        y = block(start, y + 30) + 2
        d.text((x, y), "Other agents and scripts: POST to /coder?pose=typing", font=F["small"], fill=MUTED, anchor="lm")

    def render_coder(self):
        F = self.fonts
        fb = self.fb
        now = time.monotonic()
        s = self.coder.snapshot(now)
        title, sub = self.coder_status(s)
        hints = self.coder_hints(s)
        quiet = self.setting("coder_sound") == "Off"
        ask = None if self.coder_help else self.coder_ask_shown()
        key = (self.status_sig, self.msg, ACCENT, title, sub, tuple(hints), quiet, self.coder_help, self.tab_off,
               fb.w, self.full_app(), ask and ask["id"])
        ox = max(0, (fb.w - 640) // 2)                # a wide screen: the coder in the middle, the desk all along
        oy = max(0, fb.h - 480)                       # ...a taller one: the room above it
        if key != self.coder_base[0]:                 # what doesn't move: drawn when it changes
            img, d = self.canvas()
            mark = self.tap_mark()
            self.header(img, d)
            coder_desk(img, ox, oy, bottom=fb.h if self.full_app() else None)   # (no buttons: to the bottom)
            self.bot_label(d)
            y = (CO_TOP + oy + 8 + fb.h - self.FOOTER) / 2
            d.text((24, y), title, font=F["head"], fill=TEXT, anchor="lm")
            if sub:
                d.text((24 + d.textlength(title, font=F["head"]) + 12, y + 1), sub, font=F["small"], fill=MUTED, anchor="lm")
            if quiet:
                d.text((fb.w - 24, y + 1), "Sound off", font=F["small"], fill=MUTED, anchor="rm")
            self.footer(d, hints)
            stage = img.crop((ox, oy, ox + 640, oy + 480)) if ox or oy else img   # (drawn for 640x480)
            self.coder_base = (key, img, coder_under(stage))
            self.coder_taps = self.taps_cut(mark)
        self.tap_again(getattr(self, "coder_taps", None))  # (its tabs and buttons: the web page's taps)
        img = self.coder_base[1].copy()
        if self.coder_help:                            # (the card, over an empty desk)
            self.coder_card(img)
        else:
            p = self.coder.pose(now, s)
            stage = img.crop((ox, oy, ox + 640, oy + 480)) if ox or oy else img
            coder_draw(stage, p, ACCENT, now, under=self.coder_base[2])
            coder_extras(stage, p, now, ACCENT, {"code": F["co_code"], "mark": F["big"],
                                                 "z": (F["co_z1"], F["co_z2"], F["co_z3"])})
            if ox or oy:
                img.paste(stage, (ox, oy))
            if ask is not None:                        # (its request, over it all)
                self.coder_ask_card(img, ask)
        last_key, last_count, last_t, whole_t = self.coder_shown
        if (key != last_key or getattr(fb, "frames", None) != last_count or now - last_t > 0.5
                or now - whole_t > 3 or not hasattr(fb, "show_part")):
            fb.show(img)                               # the whole picture: something else changed too
            whole_t = now
        else:
            fb.show_part(img, (CO_DIRTY[0] + ox, CO_DIRTY[1] + oy, CO_DIRTY[2] + ox, CO_DIRTY[3] + oy))   # the coder
        self.coder_shown = (key, getattr(fb, "frames", None), now, whole_t)

    # the web page passes your agent's word on (webui.py: /coder, /coder/say, /coder/hook)
    def coder_state(self):
        """GET /coder: what it's doing. (The control server's thread.)"""
        return {"ok": True, "pose": self.coder.current()}

    def web_coder(self, cmd):
        """POST /coder: your agent says what it's doing (settle: it's moved on, so its requests to use a tool from
        before were answered at the computer). (The control server's thread: answered at once.)"""
        name = cmd.get("pose")
        if cmd.get("settle") is True and self.prompts.settle():
            self.dirty = True
        if name is None and cmd.get("settle") is True:
            return {"ok": True, "pose": self.coder.current()}
        if name not in CODER_POSES:
            return {"ok": False, "error": "no such pose"}
        return {"ok": True, "pose": self.coder.ask(name)}

    def coder_say(self, data, pose):
        """POST /coder/say: a clip to say, in a pose. (status, reply), once it has been said."""
        if pose not in CODER_SAY_AS:
            return 400, {"ok": False, "error": "a clip is said talking, typing, reading, thinking or rest"}
        try:
            pcm, rate, ch = coder_wav(data)
        except ValueError as ex:
            return 415, {"ok": False, "error": str(ex)}
        return 200, {"ok": True, "ms": self.coder.say(pcm, rate, ch, pose)}
