"""Playing videos, music and radio, and what's playing now."""
import os
import random
import re
import shutil
import subprocess
import threading
import time

from ..theme import ACCENT, BODY, LINE, MUTED, ROW, TEXT
from ..config import SCREEN_MODES
from ..util import clock, probe_length
from ..screen import (aplay_device, bt_output_name, bt_outputs, slow_pi, sound_cards, sound_device, sound_name,
                      sound_place)
from ..radio import rb_get
from ..tv import hls_pick, is_hls
from ..library import (
    AUDIO_PLAYER, LIBRARY, LISTEN_KINDS, LOCAL_CACHE, NET_CACHE, PLAYER_NICE, RADIO_CACHE, resolve,
    SCREEN_KINDS, VIDEO_PLAYER, video_scale)
from ..plex import PLEX_CACHE


HUSH_RETRY = 60.0     # seconds before trying again if the speaker's silence wouldn't play
MUSIC_BACK_SECS = 2.0  # music a game or a video stopped: back this long after it's over
SOUND_LOOK = 2.0      # seconds between looks at where the sound should go, while something plays
PLAYER_SETTLE_ASK = 0.4   # a player started paused and silent: seconds between telling it to pause, till it has
PLAYER_SETTLE_MAX = 60.0  # ...and how long that goes on (a stream that never starts)


def quiet_child():
    """In a child process, before it starts: a low priority, and gone if this program goes."""
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        import ctypes
        import signal
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)        # PR_SET_PDEATHSIG
    except Exception:
        pass


class PlayerScreen:
    """Playing videos, music and radio, and what's playing now."""

    # -- the GPi Case's speaker, in the terminal -------------------------------
    def hush_tick(self, now):
        """The GPi Case's speaker makes a noise in the terminal while nothing's driving it (music playing does). So
        there, with nothing playing, it's given silence to play; music, or media mode, takes over from it."""
        want = (self.gpi_case and not self.active and self.game is None
                and not (self.proc and self.proc.poll() is None))
        on = self.hush_proc is not None and self.hush_proc.poll() is None
        if want and not on:
            if self.hush_proc is not None:             # it stopped by itself: not again for a while
                self.hush_proc, self.hush_wait = None, now + HUSH_RETRY
            if now >= self.hush_wait:
                self.hush_start()
        elif on and not want:
            self.hush_stop()

    def hush_start(self):
        if not shutil.which("aplay"):
            return
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", "2", "-r", "48000"]
        if "Headphones" in [c for c, _ in sound_cards()]:    # (the case's speaker, whatever Settings > Sound says)
            cmd += ["-D", "default:CARD=Headphones"]
        try:
            with open("/dev/zero", "rb") as zero:
                self.hush_proc = subprocess.Popen(cmd, stdin=zero, stdout=subprocess.DEVNULL,
                                                  stderr=subprocess.DEVNULL, preexec_fn=quiet_child)
        except OSError:
            self.hush_proc = None

    def hush_stop(self):
        p, self.hush_proc = self.hush_proc, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                p.kill()

    def probe_loop(self):
        while self.active:
            if self.proc_owns_screen():
                time.sleep(1)
                continue
            todo = None
            for i, tab in enumerate(LIBRARY):
                if tab["type"] == "files":
                    todo = next((it for it in self.tab_items(i)
                                 if self.length(it) is None), None)
                    if todo:
                        break
            if todo is None:
                break
            n = probe_length(todo["src"])
            try:
                mtime = os.path.getmtime(todo["src"])
            except OSError:
                continue
            with self.lock:
                self.state["dur"][todo["key"]] = [mtime, n]
            self.dirty = True
        self.save_state()

    # -- Bluetooth headphones: the sound goes where they are ------------------------------------------------
    def sound_tick(self, now):
        """Bluetooth headphones (or a speaker) connected while something plays, with Settings > Sound on Auto: its
        sound moves to them, and it plays on. The ones it played through gone: back to the Pi's own, paused, as a
        phone does (A plays on); a game brings up its menu; music in the terminal, where nothing shows it's
        paused, stops."""
        run, p = self.game, self.proc
        was = self.game_sound if run is not None else self.sound_used if p is not None else None
        if not was or (run is None and self.kind is None):
            return
        ended = run is None and p.poll() is not None
        if now < self.sound_look and not (ended and was[0] == "bluetooth"):   # (it may have stopped for that)
            return
        self.sound_look = now + SOUND_LOOK
        place = sound_place(self.setting("sound"))
        if place == was or "bluetooth" not in (place[0], was[0]):
            return                                     # (as it was: a TV unplugged, say, changes nothing)
        gone = was[0] == "bluetooth" and was[1] not in [dev for dev, _ in bt_outputs()]
        lost = (bt_output_name(was[1]) or "Bluetooth") if gone else ""
        to = (bt_output_name(place[1]) or "Bluetooth") if place[0] == "bluetooth" else sound_name(place[0])
        if run is not None:
            self.game_sound = place
            if gone and self.view == "game":
                self.game_menu_open()                  # (it waits for you)
            run.send("sound " + (aplay_device(None, place[0]) or "-"))
            self.toast(f"Paused: {lost} disconnected" if gone and self.view == "gamemenu" else
                       f"{lost} disconnected" if gone else f"Sound through {to}", 4)
            return
        if gone and not self.active:                   # (in the terminal, where it can't show it's paused: stopped)
            self.stop()
            self.resume_later = None
            return
        self.sound_used = place
        say = f"Paused: {lost} disconnected" if gone else f"Sound through {to}"
        self.start_paused = gone or self.paused        # (paused: still paused, through them)
        note = say + (". A plays on" if gone else "")  # (a video's curtain, as it starts again)
        try:
            if self.kind == "plex" and self.cur:
                self.plex_restart(self.plex_now())
            elif self.kind in ("radio", "live"):
                self.play(self.queue, self.qi, start=0, show=False, note=note)
            elif self.queue and 0 <= self.qi < len(self.queue):
                self.play(self.queue, self.qi, start=max(self.pos or 0, 0) + (0 if gone else 3), show=False, note=note)
        finally:
            self.start_paused = False
        if self.kind in SCREEN_KINDS:
            self.screen_note = (say, time.monotonic() + 8)   # (on the picture, once it's up)
        self.toast(say, 4)

    def settle_tick(self, now):
        """A player started paused and silent (muted): mplayer drops what it's told while it fills its cache, so
        it's told again and again to pause ("pausing", which leaves it paused however often it's said) until it
        says it is. Played on meanwhile (A): told its volume and to play, again and again, till it says it plays."""
        if not self.settling:
            return
        p = self.proc
        if p is None or p.poll() is not None or now - self.started > PLAYER_SETTLE_MAX:
            self.settling = False
            return
        said = self.pause_said
        if said and said[0] is p and said[1] == ("no" if self.settle_play else "yes"):
            self.settling = False
            return
        if now >= self.settle_ask:
            self.settle_ask = now + PLAYER_SETTLE_ASK
            if not self.muted:                         # (its volume back: that may not have reached it either)
                self.to_player(f"pausing_keep_force volume {self.volume} 1")
            if self.settle_play:
                self.to_player("get_property pause")       # (a line with no "pausing": it plays)
            else:
                self.to_player("pausing get_time_pos")
                self.to_player("pausing_keep_force get_property pause")

    # -- player --------------------------------------------------------------
    def cmd(self, c):
        """A line for the player. One started paused and silent (muted) may not be listening yet (it drops what it's
        told while it fills its cache): pausing and playing then go as lines that can be said again and again, and
        settle_tick says them till it answers."""
        plays = not c.startswith("pausing")            # (any line without "pausing" before it plays it)
        if self.settling and plays:
            play = c != "pause" or self.paused         # (pause: the other way from how it's shown)
            if play and self.muted:
                self.muted = False
                self.to_player(f"pausing_keep_force volume {self.volume} 1")
            self.settle_play, self.pause_said, self.settle_ask = play, None, time.monotonic() + PLAYER_SETTLE_ASK
            if c == "pause":
                c = "get_property pause" if play else "pausing get_time_pos"
        elif self.muted and plays:                     # (it'll play: its volume back first)
            self.muted = False
            self.to_player(f"pausing_keep_force volume {self.volume} 1")
            if c == "pause":
                c = "get_property pause"
        self.to_player(c)

    def to_player(self, c):
        try:
            self.proc.stdin.write(c + "\n")
            self.proc.stdin.flush()
        except (OSError, AttributeError, ValueError):
            pass

    def next_screen(self):
        """Y while a video plays: full screen on or off, kept for the next videos too (Settings >
        Video size picks zoomed or stretched). The player starts again where it was: mplayer
        can't change its scaling as it plays."""
        cur = self.setting("screen")
        if cur == "Fit":
            mode = self.state["settings"].get("full")
            mode = mode if mode in SCREEN_MODES[1:] else "Full screen"
        else:
            mode = "Fit"
            self.state["settings"]["full"] = cur              # the next Y brings this one back
        self.state["settings"]["screen"] = mode
        self.save_state()
        self.screen_note = (mode, time.monotonic() + 4)
        if self.kind == "plex":
            self.plex_restart(self.plex_now())
        elif self.kind == "live":
            self.play(self.queue, self.qi, start=0)
        else:
            self.play(self.queue, self.qi, start=max(self.pos or 0, 0) + 3)

    def osd(self, text, ms=1500):
        self.cmd(f'pausing_keep_force osd_show_text "{text}" {ms}')    # (paused, it stays paused)

    def reader(self, p):
        for line in p.stdout:
            if p is not self.proc:
                continue
            if "StreamTitle='" in line:            # song name from internet radio
                m = re.search(r"StreamTitle='(.*?)';", line)
                if m and m.group(1).strip():
                    if self.meta.get("song") != m.group(1).strip():
                        self.pop_now()             # (a new one: up on the home screen for a moment)
                    self.meta["song"] = m.group(1).strip()
                    self.dirty = True
                continue
            if not line.startswith("ANS_"):
                continue
            k, _, v = line.strip().partition("=")
            v = v.strip("'")
            if k == "ANS_VIDEO_RESOLUTION":
                m = re.search(r"(\d+)\s*x\s*(\d+)", v)
                if m and int(m.group(2)):
                    self.vsize = (int(m.group(1)), int(m.group(2)))
                continue
            if k in ("ANS_TIME_POSITION", "ANS_LENGTH"):
                try:
                    if k == "ANS_TIME_POSITION":
                        self.pos = float(v)
                    else:
                        self.meta["length"] = float(v)
                except ValueError:
                    pass
            elif k in ("ANS_META_TITLE", "ANS_META_ARTIST") and v:
                self.meta[k[9:].lower()] = v
                self.dirty = True
            elif k == "ANS_pause":
                self.pause_said = (p, v)

    def spawn(self, args, target):
        self.started = time.monotonic()
        self.voice.stop(unload=True)                   # (the player has the sound, and the memory)
        args = list(args)
        place = sound_place(self.setting("sound"))     # Settings > Sound (Auto: Bluetooth headphones, if on)
        if "-ao" in args:
            args[args.index("-ao") + 1] = sound_device(None, place[0])
        self.sound_used, self.sound_look = place, time.monotonic() + SOUND_LOOK
        paused = self.start_paused                     # (it starts paused, silent: its volume back as it plays on)
        if paused:
            if "-volume" in args:
                args[args.index("-volume") + 1] = "0"
            else:
                args += ["-volume", "0"]
        if self.fb and self.kind in SCREEN_KINDS and hasattr(self.fb, "invalidate"):
            self.fb.invalidate()                       # the picture covers the menus' black edges
        self.muted = self.settling = False
        self.proc = subprocess.Popen(
            args + [target], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
            preexec_fn=lambda: os.nice(PLAYER_NICE))
        threading.Thread(target=self.reader, args=(self.proc,), daemon=True).start()
        if paused:                                     # (paused as soon as it'll listen: settle_tick)
            self.muted = self.settling = self.paused = True
            self.settle_play, self.settle_ask, self.pause_said = False, 0.0, None

    def screen_dims(self):
        """The real screen's size (the menus are drawn 480 lines high and scaled to it)."""
        return getattr(self.fb, "real_w", 640), getattr(self.fb, "real_h", 480)

    def video_args(self):
        w, h = self.screen_dims()
        args = VIDEO_PLAYER + video_scale(self.setting("screen"), self.vsize, w, h)
        if (w, h) != (640, 480) and slow_pi():
            args += ["-sws", "0"]              # the quicker way up to a big screen
        return args

    def play(self, queue, i, start=None, show=True, note=None):
        """Plays queue[i]. Music and radio open Now playing, unless show is False (the next song, or one at
        start-up): you stay where you are. note: what a video's curtain says as it starts, instead."""
        if queue[i]["kind"] in ("plexvideo", "jfvideo"):
            return self.play_plex(queue, i)
        self.stop()
        it = queue[i]
        if queue is not self.queue:
            self.queue_random = False                  # (random_song says when it is)
        self.queue, self.qi = queue, i
        kind = it["kind"]
        if start is None:
            start = self.resume_at(it)
            self.vsize = None
        if kind in LISTEN_KINDS:
            self.pop_now()
            self.resume_later = None                   # (music again: nothing stopped to bring back)
            if show:
                self.close_viewer()
                self.view, self.now_from = "now", "list"
        elif self.active:
            status = note or (f"Resuming at {clock(start)}" if start else
                              "Connecting" if kind == "live" or it["src"].startswith("ia:")
                              else "Starting")
            self.render_wait(it["title"], status, playing=True)
        plexlive = it["src"].startswith("plexlive:")
        try:
            target = (self.plex.live_url(it["src"][len("plexlive:"):]) if plexlive
                      else resolve(it))
        except Exception:
            self.view = "list"
            self.toast("Couldn't load that. Check the WiFi connection.")
            return
        if kind == "live" and not plexlive and is_hls(target):     # the version that suits the Pi
            target = hls_pick(target)
        net = "://" in target
        args = list(AUDIO_PLAYER if kind in LISTEN_KINDS else self.video_args())
        if kind == "radio":
            args += RADIO_CACHE
        elif plexlive:
            args += PLEX_CACHE
        else:
            args += NET_CACHE if net else ([] if kind == "audio" else LOCAL_CACHE)
        args += ["-volume", str(self.volume)]
        if start:
            args += ["-ss", str(int(max(start - 3, 0)))]
        self.retry = None
        if kind == "radio":
            if target.startswith("https://"):
                # plain http lets mplayer show the song name; fall back to https if refused
                self.retry = (args, "ffmpeg://" + target)
                target = "http://" + target[len("https://"):]
        elif net:
            target = "ffmpeg://" + target        # lets mplayer open https and HLS
        self.kind, self.cur, self.pos, self.meta, self.paused = kind, it, start, {}, False
        self.next_query = time.monotonic() + 1
        if kind == "video" and self.shrinker.status(it["src"]):      # (said once the picture's up)
            self.screen_note = ("Still being made smaller: it may stutter", time.monotonic() + 8)
        if kind == "radio" and it.get("uuid"):          # Radio Browser counts what people play
            threading.Thread(target=lambda u=it["uuid"]: rb_get(f"/json/url/{u}"), daemon=True).start()
        self.spawn(args, target)
        if kind == "audio":
            for c in ("get_meta_title", "get_meta_artist", "get_time_length"):
                self.cmd("pausing_keep_force " + c)
        elif kind not in LISTEN_KINDS:
            self.cmd("pausing_keep_force get_video_resolution")
            if kind == "video":
                self.cmd("pausing_keep_force get_time_length")
        self.dirty = True

    def random_song(self):
        """Settings > Random song at start-up: one of your songs from ~/Music, and the rest after it in a random
        order, while you carry on (in the terminal too). Not if something's playing already."""
        mi = next((k for k, t in enumerate(LIBRARY) if t["type"] == "files" and t.get("kind") == "audio"), None)
        if mi is None or self.proc or self.game is not None:
            return
        if mi not in self.items:
            self.load_tab(mi)
        songs = list(self.tab_items(mi))
        if not songs:
            if self.active:
                self.toast("No songs in ~/Music to play at start-up", 4)
            return
        random.shuffle(songs)
        self.play(songs, 0, show=False)
        self.queue_random = True

    def remember(self, finished=False):
        it, self.cur = self.cur, None
        if not it or it["kind"] != "video":
            return
        with self.lock:
            if finished:
                self.state["pos"][it["key"]] = -1
            elif self.pos > 5:
                self.state["pos"][it["key"]] = round(self.pos, 1)
        self.save_state()

    def music_loops(self):
        """Settings > Random song at start-up keeps your music going: the songs go round and round, and what a game
        or a video stopped comes back after it."""
        return self.setting("start_song") == "On"

    def stop(self):
        if (self.proc and self.proc.poll() is None and self.kind in LISTEN_KINDS and self.cur and not self.paused
                and self.music_loops()):                # (to come back once whatever stopped it is over)
            self.resume_later = (self.queue, self.qi, self.pos if self.kind == "audio" else 0)
        self.game_end()
        p, self.proc = self.proc, None
        self.muted, self.settling, self.sound_used = False, False, None
        if p and p.poll() is None:
            try:
                p.stdin.write("quit\n")
                p.stdin.flush()
                p.wait(timeout=2)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                p.kill()
        if self.kind == "plex" and self.cur:
            pos, length = self.plex_now(), self.cur.get("dur") or 0
            self.plex_finish(self.cur, pos, self.plex_session, bool(length) and pos > length * 0.9)
            self.cur = None
            self.plex_pending = None
        self.remember()
        self.kind = None
        self.retry = None

    def next_index(self, d):
        n = len(self.queue)
        if not n:
            return None
        if self.kind in ("radio", "live"):          # channel up/down wraps around
            return (self.qi + d) % n
        if self.kind == "audio" and self.shuffle and d > 0 and n > 1:
            return random.choice([i for i in range(n) if i != self.qi])
        i = self.qi + d
        if not 0 <= i < n and self.kind == "audio" and self.music_loops():   # round again
            if i >= n and self.queue_random:
                self.reshuffle()
            return i % n
        return i if 0 <= i < n else None

    def reshuffle(self):
        """The start-up's random songs in a new order for the next time round (not the one just played first)."""
        last = self.queue[self.qi] if 0 <= self.qi < len(self.queue) else None
        random.shuffle(self.queue)
        if len(self.queue) > 1 and self.queue[0] is last:
            self.queue[0], self.queue[-1] = self.queue[-1], self.queue[0]

    def music_back(self, now):
        """Music a game or a video stopped (Settings > Random song at start-up on) starts again a moment after
        it's over: the same song from where it was, or the same station. In media mode, while nothing else plays
        and the bot isn't talking."""
        if not (self.resume_later and self.active and self.proc is None and self.game is None
                and not self.voice.speaking and not self.halting):
            self.resume_at_t = None
            return
        if self.resume_at_t is None:
            self.resume_at_t = now + MUSIC_BACK_SECS
        elif now >= self.resume_at_t:
            queue, qi, pos = self.resume_later
            self.resume_later, self.resume_at_t = None, None
            if self.music_loops() and 0 <= qi < len(queue):
                self.play(queue, qi, start=pos if pos > 5 else 0, show=False)

    def skip(self, d):
        i = self.next_index(d)
        if i is not None:
            self.play(self.queue, i)
        else:
            self.stop()
            self.view = "list"
            self.dirty = True

    def set_volume(self, d):
        self.volume = max(0, min(100, self.volume + d))
        if not self.muted:                             # (paused and silent: it gets this volume as it plays on)
            self.cmd(f"pausing_keep volume {self.volume} 1")
        self.dirty = True

    def render_now(self):
        F = self.fonts
        img, d = self.canvas()
        W = self.fb.w
        it = self.cur or {"title": "", "src": "", "sub": ""}
        radio = self.kind == "radio"
        self.title_row(d, "Now playing", "Shuffle" if self.shuffle and not radio else
                       ("LIVE" if radio else None), ACCENT)

        cx, cy, cs = 24, self.LIST_TOP + 20 + max(0, self.fb.h - 480) // 3, 160   # (a taller screen: lower down)
        d.rounded_rectangle((cx, cy, cx + cs, cy + cs), radius=16, fill=ROW)
        if radio:   # a little broadcast symbol
            ox, oy = cx + cs / 2, cy + cs / 2 + 18
            d.ellipse((ox - 9, oy - 9, ox + 9, oy + 9), fill=ACCENT)
            for r in (26, 44, 62):
                d.arc((ox - r, oy - r, ox + r, oy + r), 225, 315, fill=ACCENT, width=5)
        else:
            d.text((cx + cs / 2, cy + cs / 2), "♪", font=F["note"], fill=ACCENT, anchor="mm")

        tx, tw = cx + cs + 28, W - (cx + cs + 28) - 24
        if radio:
            title = it["title"]
            sub = self.meta.get("song") or it.get("sub") or ""
        else:
            title = self.meta.get("title") or it["title"]
            sub = self.meta.get("artist") or os.path.basename(os.path.dirname(it["src"]))
        y = cy + 18
        for l in self.wrap(d, title, F["big"], tw, 2):
            d.text((tx, y), l, font=F["big"], fill=TEXT, anchor="lm")
            y += 32
        if sub:
            for l in self.wrap(d, sub, F["row"], tw, 2 if radio else 1):
                d.text((tx, y + 2), l, font=F["row"], fill=BODY, anchor="lm")
                y += 28
        what = "Station" if radio else "Track"
        d.text((tx, y + 10), f"{what} {self.qi + 1} of {len(self.queue)}",
               font=F["small"], fill=MUTED, anchor="lm")
        d.text((tx, cy + cs - 10), ("Paused" if self.paused else f"Volume {self.volume}"),
               font=F["small"], fill=ACCENT if self.paused else MUTED, anchor="lm")

        by = cy + cs + 44
        if not radio:
            length = self.meta.get("length") or self.length(it) or 0
            d.rounded_rectangle((24, by, W - 24, by + 5), radius=2, fill=LINE)
            if length:
                frac = min(self.pos / length, 1)
                d.rounded_rectangle((24, by, 24 + (W - 48) * frac, by + 5), radius=2, fill=ACCENT)
            d.text((24, by + 22), clock(self.pos), font=F["small"], fill=BODY, anchor="lm")
            if length:
                d.text((W - 24, by + 22), clock(length), font=F["small"], fill=MUTED, anchor="rm")
            if not self.shuffle and self.qi + 1 < len(self.queue):
                nxt = self.fit(d, "Next: " + self.queue[self.qi + 1]["title"], F["small"], W - 48)
                d.text((24, by + 58), nxt, font=F["small"], fill=MUTED, anchor="lm")
            hints = [("A", "Play/pause" if not self.paused else "Play"), ("◀▶", "Seek"),
                     ("L R", "Prev/next"), ("Y", "Shuffle"), ("B", "List")]
        else:
            hints = [("A", "Pause" if not self.paused else "Play"), ("◀▶", "Station"),
                     ("▲▼", "Volume"), ("B", "List")]
        self.footer(d, hints)
        self.fb.show(img)
