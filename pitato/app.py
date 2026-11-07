"""The main loop: terminal mode (buttons as keys) and media mode, and starting up."""
import selectors
import signal
import time
from evdev import ecodes as e, UInput

from .config import move_old_places
from .handheld import profile as handheld_profile
from .library import MENU_RATE, MENU_REPEAT, SCREEN_KINDS
from .inputs import (
    AB, BUTTONS, CHORD_WAIT, Keys, MEDIA_TOGGLE, NAME, Pads, PowerKey, REPEAT, REPEAT_DELAY, REPEAT_RATE, STAR,
    STAR_TAP, TERMINAL, Touch)
from .control import Control, control_key, serve_control
from .media import Media
from .pilot import changes, PILOT_MOST, Pilots


NEVER = float("inf")
HOT_HELD = 10.0  # HOME down in the menus this long without letting go: as if it had (◀ or ▶ go as themselves)


# ---- the main loop ----------------------------------------------------------------------
def run(ui, media, control=None, stop=None):
    """Controllers (plugged in or out at any time), the web page's requests and media mode's
    clock. stop() returning True ends it (the tests use that)."""
    held = {}        # button name -> [keys, next_repeat_time]  (terminal mode)
    menu_held = {}   # button name -> next_repeat_time            (media screens)
    pending = {}     # (pad, "select" or "start") -> when it goes out, unless the other comes first
    chorded = set()  # (pad, button) pressed as SELECT + START: its release goes nowhere
    star = {}        # pad -> [when its star went down, whether another button went with it]
    hot = {}         # HOME down in the menus: {"at": when, "used": another button went with it (Konami code)}
    was = {"learning": False, "keys": False}
    pilots = Pilots()                 # your other Pietatos controlling this one (pilot.py)
    via = {"from": None}              # where the button being handled now is from: "here" (a controller or keyboard of
                                      # this one's), "pilot" (another of yours controlling this one: never sent on)

    def sent_on(name, down):
        """Controlling another of your Pietatos (Home > Control another Pietato): a button from a controller or a
        keyboard here goes to it instead (True). One from another of yours controlling this one never does (two
        controlling each other would send it round and round), nor does one from the web page's remote or a touch."""
        if via["from"] != "here" or not media.pilot_on():
            return False
        media.pilot_press(name, down)
        return True

    def key_down(name):
        keys = TERMINAL[name]
        for k in keys:
            ui.write(e.EV_KEY, k, 1)
        ui.syn()
        t = time.monotonic() + REPEAT_DELAY if keys[-1] in REPEAT else NEVER
        held[name] = [keys, t]

    def key_up(name):
        item = held.pop(name, None)
        if item:
            for k in reversed(item[0]):
                ui.write(e.EV_KEY, k, 0)
            ui.syn()

    def can_repeat():
        return (media.active and media.view in Media.REPEAT_VIEWS
                and media.kind not in SCREEN_KINDS and not media.holds_buttons())

    def toggle(to=None):
        """Media mode on or off (HOME)."""
        for n in list(held):
            key_up(n)
        menu_held.clear()
        to = to or ("terminal" if media.active else "media")
        if to == "media" and not media.active:
            media.enter()
        elif to == "terminal" and media.active:
            media.leave()

    def home():
        """HOME: in a game, the game's menu (or back to the game); cmatrix or hollywood stops; Chromium's menu (or
        back to Chromium); on a picture, a PDF or some text, a video or Now playing (or a song, a video or a picture
        picked in a list), its menu while another of your Pietatos is on (or back to it). In the terminal: media
        mode again. On its own it never goes to the terminal: HOME and ◀ does (button()). The screen resting: it
        wakes, and that's all. Controlling another of yours: a press of HOME there."""
        if sent_on(MEDIA_TOGGLE, True):               # (the GPi Case's star, tapped: HOME, there)
            sent_on(MEDIA_TOGGLE, False)
            return
        if media.active and media.resting:            # (TURBO tapped, or SELECT and START: as HOME)
            media.stir()
            return
        if media.active and (media.game_home() or media.prog_home() or media.chromium_home() or media.konami_home()
                             or media.file_home() or media.media_home()):
            menu_held.clear()
            return
        if media.active:                              # (HOME on its own here once went to the terminal: said how now)
            media.toast("For the terminal, hold HOME and press ◀", 3)
            return
        toggle()

    def hotkey(down):
        """HOME (or SELECT and START together). In the menus it does its thing as you let go of it, unless another
        button's pressed with it: ◀ goes to the terminal, ▶ is Konami code's (the box for one of your codes), and HOME
        does nothing else. Anywhere else, as it goes down. Controlling another of yours: its HOME (held long, it lets
        go of it)."""
        if sent_on(MEDIA_TOGGLE, down):
            return
        if down:
            hot.clear()
            if media.active and media.konami_hotkey_ok():
                hot.update(at=time.monotonic(), used=False)
                return
            home()
            return
        was_hot = dict(hot)
        hot.clear()
        if was_hot and not was_hot["used"]:
            home()

    def button(name, down, pad=None):
        """A button, from a controller (pad: which, for a game's players) or the web page's remote."""
        if name != MEDIA_TOGGLE and sent_on(name, down):   # (controlling another of yours: its, not this one's)
            return
        if down and media.active and media.resting:   # (the screen resting: a press wakes it, and does nothing else)
            media.stir()
            return
        if name == MEDIA_TOGGLE:
            hotkey(down)
            return
        if down and hot:                               # HOME held in the menus: this button with it
            if time.monotonic() - hot["at"] > HOT_HELD:
                hot.clear()                            # (its letting go never came: as if it had)
            elif not hot["used"]:
                hot["used"] = True
                if name == "left":                     # (HOME and ◀: the terminal)
                    toggle("terminal")
                    return
                if name == "right" and media.konami_listen():   # (HOME and ▶: the box for one of your codes)
                    return
        if media.active:
            media.input_pad = pad
            try:
                if down:
                    if media.press(name) == "exit":
                        menu_held.clear()
                        media.leave()
                    elif name in MENU_REPEAT and can_repeat():
                        menu_held[name] = time.monotonic() + REPEAT_DELAY
                else:
                    menu_held.pop(name, None)
                    media.release(name)
            finally:
                media.input_pad = None
            return
        if name in TERMINAL:
            key_down(name) if down else key_up(name)

    def pad_button(pad, name, down):
        """A controller without HOME: SELECT and START together stand in for it. The GPi Case's
        star, if the case sends it: with HOME, HOME just once; on its own, a quick press, HOME;
        held while other buttons go (the case's turbo), nothing."""
        if name == STAR:
            if down:
                star[pad.path] = [time.monotonic(), bool(pad.down - {STAR})]   # HOME down already: done
            else:
                t, used = star.pop(pad.path, (0.0, True))
                if not used and time.monotonic() - t <= STAR_TAP:
                    home()
            return
        if down and pad.path in star:
            star[pad.path][1] = True                   # with the star: HOME goes out as itself, once
        other = {"select": "start", "start": "select"}.get(name)
        if other is None or pad.home:
            button(name, down, pad)
            return
        k, ko = (pad.path, name), (pad.path, other)
        if not down:
            if k in chorded:
                chorded.discard(k)
                if ko in chorded:                      # (the first of the two let go: HOME, let go)
                    hotkey(False)
                return
            if pending.pop(k, None) is not None:       # a quick press: it goes out now
                button(name, True, pad)
            button(name, False, pad)
            return
        if other in pad.down and ko not in chorded:    # both down: HOME
            if pending.pop(ko, None) is None:
                button(other, False, pad)              # it went out already: let it go
            chorded.update((k, ko))
            hotkey(True)
            return
        pending[k] = time.monotonic() + CHORD_WAIT

    def learn_check():
        """Settings > Controller takes every press while it runs: each controller starts afresh
        when it begins and ends, with nothing waiting to go out."""
        now_learning = media.learning
        if was["learning"] != now_learning:
            pending.clear()
            chorded.clear()
            star.clear()
            hot.clear()
            if not now_learning:
                for p in pads.by_path.values():
                    p.now, p.down = {}, set()
        was["learning"] = now_learning

    def pad_event(pad, ev):
        media.web_guard = False                        # someone at the Pi has it
        learn_check()
        if media.learning:                             # Settings > Controller has it
            media.learn_event(pad, ev)
            return
        sticks = media.game_sticks()                   # an N64 or PSP game: the sticks go to it as they are
        if sticks:
            moved = pad.stick(ev)
            if moved:
                media.game_stick(*moved, pad=pad)      # (this controller's player's)
                return
        elif media.chromium_sticks() and pad.dpad_apart():   # Chromium: its pointer and its wheel, as they're pushed
            moved = pad.stick(ev)                      # (a d-pad that's a stick's axes is its d-pad, as the GPi Case's)
            if moved:
                media.chromium_stick(*moved)
                return
        for name, down in pad.translate(ev):
            if down and time.monotonic() < media.halting:
                continue                               # shutting down: let go of things, no more
            if down:
                media.pad_used = pad                   # (the one in hand: Settings > Swap A and B's)
            if sticks:
                name = media.game_pad_button(pad, name)
                if name is None:
                    continue                           # (the d-pad, as the stick)
            pad_button(pad, name, down)

    def typing():
        """A text box is up, or the TV remote's number pad, or Notes: a keyboard types into it (KeyReader has it)."""
        return media.view == "keys" or getattr(media, "remote_pad", None) is not None or media.notes_typing()

    def keyboard_event(kb, ev):
        """A keyboard's key: in media mode, a button (W A S D the d-pad...). In the terminal, and while cmatrix or
        the others, a text box or Settings > Controller has it, its keys are its own. Its trackpad (or a mouse):
        media mode's, cmatrix's and a text box's too (it types nothing of its own), but not Settings > Controller's.
        While Chromium's in front, keys and mouse are Chromium's own."""
        pointer = kb.pointer(ev)
        if (not media.active or media.learning or media.chromium_shown()            # (Chromium's, while it's in front)
                or (not pointer and (media.prog is not None or typing()))):
            for name in kb.let_go("pointer" if pointer else "keys"):   # (nothing stays held down)
                button(name, False)
            return
        out = kb.translate(ev)
        if out or not pointer:
            media.web_guard = False                    # someone at the Pi has it
        for name, down in out:
            if down and time.monotonic() < media.halting:
                continue                               # shutting down: let go of things, no more
            button(name, down)                         # (in a game: player 1, as the web page's remote is)

    def touch_event(touch, ev):
        """The touch screen: in media mode, a tap or a swipe, as on the web page's copy of the screen (the resting
        screen woken, and nothing else). Not the terminal's, Settings > Controller's, or Chromium's while it's in
        front (it reads the screen's touches itself)."""
        if not media.active or media.learning or media.chromium_shown():
            touch.forget()
            return
        for gesture in touch.translate(ev):
            media.web_guard = False                    # someone at the Pi has it
            if media.resting:
                media.stir()
                continue
            media.stir()
            cmd = media.touch_cmd(gesture)
            if cmd is None:
                continue
            names, _ = media.web_touch(cmd)
            for name in names:                         # (what it stands for: pressed as the remote's buttons are)
                if name in BUTTONS:
                    button(name, True)
                    button(name, False)

    def keys_check():
        """A text box (or the number pad) just opened: the keyboards are its own while it's up (KeyReader; their keys
        let go of there, a trackpad in with one too), so what they're holding down is let go of here now, not left
        stuck."""
        now_keys = media.active and typing()
        if now_keys and not was["keys"]:
            for kb in pads.keyboards.values():
                if not kb.mouse:
                    for name in kb.let_go():
                        button(name, False)
        was["keys"] = now_keys

    def keyboard_gone(kb):
        hot.clear()                                    # (its HOME, if it was held: nothing more)
        media.pilot_let_go()
        pads.drop(kb)
        print(f"{'mouse' if kb.mouse else 'keyboard'} gone: {kb.dev.name}", flush=True)
        for name in kb.let_go():
            button(name, False)

    def found(new, quiet=False):
        media.keyreader.exclude = set(pads.by_path)
        if pads.notice:                                # (a GPi Case's buttons looked for again: said on the screen)
            if media.active and not media.proc_owns_screen():
                media.toast(pads.notice, 5)
            pads.notice = None
        if new:
            media.dirty = True
            if not quiet:
                media.stir()                           # (something plugged in: someone's there)
            if not quiet and media.active and not media.proc_owns_screen():
                named = [d for d in new if not getattr(d, "mouse", False)] or new   # (a keyboard and its trackpad:
                media.toast(f"{named[-1].dev.name} connected", 2)                  # the keyboard's name)

    def here(fn, *args):
        """fn(*args) for a controller or keyboard of this one's: what it presses goes to another of yours, while this
        one's controlling it."""
        via["from"] = "here"
        try:
            fn(*args)
        finally:
            via["from"] = None

    def lost(pad):
        hot.clear()                                    # (its HOME, if it was held: nothing more)
        media.pilot_let_go()                           # (controlling another: what it held, let go of there too)
        pads.drop(pad)
        print(f"controller gone: {pad.dev.name}", flush=True)
        mine = {k for k in list(pending) + list(chorded) if k[0] == pad.path}
        star.pop(pad.path, None)
        for name in list(pad.down):
            if (pad.path, name) not in mine and name != STAR:
                button(name, False, pad)               # nothing stays held down
        pad.down.clear()
        for k in mine:
            pending.pop(k, None)
            chorded.discard(k)
        if media.learn and media.learn.get("pad") is pad:
            media.cancel_learn("The controller was unplugged")
        found([])
        media.dirty = True

    # -- another of your Pietatos controlling this one (pilot.py): a controller of its own here ----------------------
    def pilot_button(pad, name, down):
        """A button from another of yours controlling this one: as one from a controller plugged in here (its
        player's, in a game). But as the web page's remote's, it works media mode only, never the terminal (HOME
        brings media mode back), and it can't answer your coding agent."""
        media.web_guard = "pilot"
        learn_check()
        if not media.active and name != MEDIA_TOGGLE:
            return
        if down and time.monotonic() < media.halting:
            return                                     # (shutting down: let go of things, no more)
        if pad.swapped:
            name = AB.get(name, name)                  # (Settings > Swap A and B, on it)
        if down:
            pad.down.add(name)
            media.pad_used = pad                       # (the one in hand: Settings > Swap A and B's)
        else:
            pad.down.discard(name)
        if media.game_sticks():
            name = media.game_pad_button(pad, name)    # (an N64 game: the d-pad's the stick)
            if name is None:
                return
        via["from"] = "pilot"
        try:
            button(name, down, pad)
        finally:
            via["from"] = None

    def pilot_gone(sess, why):
        """One of yours has stopped controlling this one (why: "bye"; "gone", quiet too long; "again", asking again):
        what it held let go of, and its controller gone."""
        pilots.remove(sess)
        holding = sess.holding()
        if MEDIA_TOGGLE in holding:
            hot.clear()                                # (its HOME, if it was held: nothing more)
        sess.held, sess.lost = set(), True
        for name, down in changes(holding, sess.counts, set(), sess.counts):
            pilot_button(sess.pad, name, down)
        pads.by_path.pop(sess.pad.path, None)
        media.keyreader.exclude = set(pads.by_path)
        if not pilots.sessions and pilots.sock is not None:
            try:
                sel.unregister(pilots.sock)
            except (KeyError, ValueError):
                pass
            pilots.close()
        media.pilot_ended(sess.name, why, not pilots.sessions)

    def pilot_take(events):
        for what in events:
            sess = what[1]
            if sess not in pilots.sessions:
                continue                               # (gone a moment ago)
            if what[0] == "press":
                pilot_button(sess.pad, what[2], what[3])
            else:
                pilot_gone(sess, what[0])

    def pilot_ask(cmd):
        """Another of your Pietatos asks to control this one: the port and key for its buttons (a controller of its
        own here, from now). Or it lets go of this one (end)."""
        may = media.pilot_may(cmd)
        if "addr" not in may:
            return may
        addr, name = may["addr"], may["name"]
        if cmd.get("kind") == "end":
            sess = pilots.find(cmd.get("key"), addr)
            if sess is not None:
                pilot_gone(sess, "bye")
            return {"ok": True}
        old = pilots.of(addr)
        if old is not None:
            pilot_gone(old, "again")                   # (asking again: restarted, say)
        has = cmd.get("has")
        sess = pilots.add(addr, name, has if isinstance(has, list) else None, time.monotonic())
        if sess is None:
            return {"ok": False, "error": f"{PILOT_MOST} of your Pietatos are controlling it already"}
        try:
            if pilots.open():
                sel.register(pilots.sock, selectors.EVENT_READ, pilots)
        except OSError as ex:
            pilots.remove(sess)
            print(f"pilot: no port for its buttons ({ex})", flush=True)
            return {"ok": False, "error": "It couldn't open a port for the buttons"}
        sess.pad.apply(pads.saved.get(sess.pad.ident))  # (Settings > Swap A and B on it, kept from before)
        pads.by_path[sess.pad.path] = sess.pad
        media.keyreader.exclude = set(pads.by_path)
        media.pilot_began(name, len(pilots.sessions) == 1)
        return {"ok": True, "port": pilots.port, "key": sess.key}

    def handle(cmd):
        """One request from the web page. It works media mode, never the terminal."""
        if time.monotonic() < media.halting:
            return {"error": "The Pi is shutting down"}
        c = cmd.get("cmd")
        if c not in ("websound", "webmic"):            # (webui.py's own word, not someone on the web page)
            media.web_guard = True
            if c in ("tap", "swipe", "scroll") and media.active and media.resting:
                media.stir()                           # (the screen resting: a touch wakes it, and does nothing else)
                return {"ok": True}
            if c != "press":                           # (a press wakes it as a button does)
                media.stir()
        if c == "press":
            name = cmd.get("button")
            if name not in BUTTONS:
                return {"error": "No such button"}
            if not media.active and name != MEDIA_TOGGLE:
                return {"error": "The remote works in media mode. Press Home to open it."}
            if cmd.get("repeat"):                      # held down on the page
                if media.active and media.takes_repeats(name):
                    media.press(name, repeat=True)
                    return {"ok": True}
                if name not in MENU_REPEAT:
                    return {"ok": True}
                if media.active:
                    if can_repeat():
                        media.press(name, repeat=True)
                    return {"ok": True}
            media.here_begin(cmd.get("here") is True)  # (Play here: what it starts plays on the web page instead)
            try:
                button(name, True)
                button(name, False)
            finally:
                out = media.here_end({"ok": True})
            return out
        if c == "pilot":                               # (another of yours: to control this one, or not any more)
            return pilot_ask(cmd)
        if c == "mode":
            to = cmd.get("to")
            if to not in ("media", "terminal"):
                return {"error": "No such mode"}
            toggle(to)
            if to == "media" and not media.active:
                return {"error": "There's no screen for media mode"}
            return {"ok": True}
        if c in ("tap", "swipe", "scroll", "type"):    # the web page's copy of the screen, touched (or typed under)
            if not media.active:
                return {"error": "The screen works in media mode. Press Home to open it."}
            media.here_begin(cmd.get("here") is True)  # (Play here: what it starts plays on the web page instead)
            out = {"ok": True}
            try:
                names, out = media.web_touch(cmd)
                for name in names:                     # (what it stands for: pressed as the remote's buttons are)
                    if name in BUTTONS:
                        button(name, True)
                        button(name, False)
            finally:
                out = media.here_end(out)
            return out
        if not media.active:
            for n in list(held):
                key_up(n)
        return media.web_command(cmd)

    sel = selectors.DefaultSelector()
    pads = Pads(sel)
    media.pads = pads
    if control is not None:
        sel.register(control.r, selectors.EVENT_READ, "control")
    if getattr(media, "wake_r", None) is not None:
        sel.register(media.wake_r, selectors.EVENT_READ, "wake")   # (a camera's new picture: drawn at once)
    found(pads.scan(time.monotonic(), force=True), quiet=True)
    if media.boot_media:                          # Settings: open on the home screen
        media.boot_media = False
        media.enter()
        if media.boot_game:                       # ...or in the game you played last, from where you were
            media.boot_game = False
            media.game_boot()

    try:
        while not (stop and stop()):
            nxt = min([t for _, t in held.values()] + list(menu_held.values()) + list(pending.values())
                      + [pads.next_scan, pilots.next_due()])
            timeout = max(0.0, nxt - time.monotonic())
            if media.active or media.proc or media.learn:
                timeout = min(timeout, media.tick_limit())

            for key, _ in sel.select(timeout):
                if key.data == "wake":
                    media.woken()
                    continue
                if key.data == "control":
                    for job in control.take():
                        out = {"error": "Something went wrong on the Pi"}
                        try:
                            out = handle(job["cmd"])
                            learn_check()
                            media.flush()             # so the next picture of the screen shows it
                        except Exception as ex:
                            print(f"web page request {job['cmd'].get('cmd')}: {ex!r}", flush=True)
                        finally:
                            control.done(job, out)
                    continue
                if key.data is pilots:                 # (another of yours controlling this one: its buttons)
                    pilot_take(pilots.take(time.monotonic()))
                    continue
                if isinstance(key.data, Keys):
                    kb = key.data
                    if pads.keyboards.get(kb.path) is not kb:
                        continue                       # gone a moment ago
                    try:
                        events = list(kb.dev.read())
                    except BlockingIOError:
                        continue
                    except OSError:
                        keyboard_gone(kb)
                        continue
                    for ev in events:
                        here(keyboard_event, kb, ev)
                    continue
                if isinstance(key.data, Touch):
                    touch = key.data
                    if pads.touches.get(touch.path) is not touch:
                        continue                       # gone a moment ago
                    try:
                        events = list(touch.dev.read())
                    except BlockingIOError:
                        continue
                    except OSError:
                        pads.drop(touch)
                        print(f"touch screen gone: {touch.dev.name}", flush=True)
                        continue
                    for ev in events:
                        touch_event(touch, ev)
                    continue
                if isinstance(key.data, PowerKey):
                    switch = key.data
                    if pads.power.get(switch.path) is not switch:
                        continue
                    try:
                        events = list(switch.dev.read())
                    except BlockingIOError:
                        continue
                    except OSError:
                        pads.drop(switch)
                        continue
                    if switch.switched_off(events):
                        media.power_off()
                    continue
                pad = key.data
                if pads.by_path.get(pad.path) is not pad:
                    continue                           # unplugged a moment ago
                try:
                    events = list(pad.dev.read())
                except BlockingIOError:
                    continue
                except OSError:
                    lost(pad)
                    continue
                for ev in events:
                    here(pad_event, pad, ev)

            keys_check()
            found(pads.scan(time.monotonic()))
            if pilots.sessions:
                pilot_take(pilots.check(time.monotonic()))   # (one gone quiet: what it held let go of; then it's gone)
            media.tick()
            learn_check()

            now = time.monotonic()
            for k, t in list(pending.items()):
                if now >= t:                          # SELECT or START alone: out it goes
                    del pending[k]
                    here(button, k[1], True, pads.by_path.get(k[0]))
            for item in held.values():
                if now >= item[1]:
                    ui.write(e.EV_KEY, item[0][-1], 2)
                    ui.syn()
                    item[1] = now + REPEAT_RATE
            for name, t in list(menu_held.items()):
                if now >= t:
                    if not can_repeat():
                        menu_held.pop(name, None)
                    else:
                        media.press(name, repeat=True)
                        menu_held[name] = now + MENU_RATE

            media.flush()
    finally:
        for pad in (list(pads.by_path.values()) + list(pads.power.values()) + list(pads.keyboards.values())
                    + list(pads.touches.values())):
            pads.drop(pad)
        pilots.close()
        sel.close()


def main():
    hand = handheld_profile()                      # (what this is, from its device tree: an RK3326 handheld, or not)
    if hand:
        print(f"handheld: {hand['name']} ({hand['model'] or 'no model'}, {hand['chip']}): its gamepad, screen, "
              "battery and WiFi dongle", flush=True)
    keys = sorted({k for combo in TERMINAL.values() for k in combo})
    ui = UInput({e.EV_KEY: keys}, name=NAME)
    move_old_places()                              # (what it kept by its old name: where it keeps it now)
    media = Media()
    media.shrinker.start()                         # (big videos made smaller, in the background)
    media.updater.start()                          # (a newer version looked for now and then: System > Update software)
    media.share_start()                            # (your other Pietatos told it's here: what it fetches, shared)
    media.dock_start()                             # (a GPi Case 2: its dock watched, the picture following it)
    media.chromium_leftover()                      # (Chromium, if the last Pietato left it running: closed)
    control = Control()
    serve_control(media, control, key=control_key())

    def on_term(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, on_term)

    try:
        while True:
            try:
                run(ui, media, control)
            except OSError as ex:
                print(f"input trouble ({ex}), starting again", flush=True)
                time.sleep(1)
    finally:
        media.shutdown()       # never leave the screen stuck in media mode
