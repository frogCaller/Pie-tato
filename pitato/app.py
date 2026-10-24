"""The main loop: terminal mode (buttons as keys) and media mode, and starting up."""
import selectors
import signal
import time
from evdev import ecodes as e, UInput

from .config import move_old_places
from .library import MENU_RATE, MENU_REPEAT, SCREEN_KINDS
from .inputs import (
    BUTTONS, CHORD_WAIT, MEDIA_TOGGLE, NAME, Pads, PowerKey, REPEAT, REPEAT_DELAY, REPEAT_RATE, STAR, STAR_TAP,
    TERMINAL)
from .control import Control, control_key, serve_control
from .media import Media


NEVER = float("inf")


# ---- the main loop ----------------------------------------------------------------------
def run(ui, media, control=None, stop=None):
    """Controllers (plugged in or out at any time), the web page's requests and media mode's
    clock. stop() returning True ends it (the tests use that)."""
    held = {}        # button name -> [keys, next_repeat_time]  (terminal mode)
    menu_held = {}   # button name -> next_repeat_time            (media screens)
    pending = {}     # (pad, "select" or "start") -> when it goes out, unless the other comes first
    chorded = set()  # (pad, button) pressed as SELECT + START: its release goes nowhere
    star = {}        # pad -> [when its star went down, whether another button went with it]
    was = {"learning": False}

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
        """HOME: media mode on or off; in a game, the game's menu (or back to the game); cmatrix or hollywood
        stops."""
        if media.active and (media.game_home() or media.prog_home()):      # (cmatrix, hollywood: it stops)
            menu_held.clear()
            return
        toggle()

    def button(name, down, pad=None):
        """A button, from a controller (pad: which, for a game's players) or the web page's remote."""
        if name == MEDIA_TOGGLE:
            if down:
                home()
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
                return
            if pending.pop(k, None) is not None:       # a quick press: it goes out now
                button(name, True, pad)
            button(name, False, pad)
            return
        if other in pad.down and ko not in chorded:    # both down: HOME
            if pending.pop(ko, None) is None:
                button(other, False, pad)              # it went out already: let it go
            chorded.update((k, ko))
            home()
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

    def found(new, quiet=False):
        media.keyreader.exclude = set(pads.by_path)
        if new:
            media.dirty = True
            if not quiet and media.active and not media.proc_owns_screen():
                media.toast(f"{new[-1].dev.name} connected", 2)

    def lost(pad):
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

    def handle(cmd):
        """One request from the web page. It works media mode, never the terminal."""
        if time.monotonic() < media.halting:
            return {"error": "The Pi is shutting down"}
        media.web_guard = True
        c = cmd.get("cmd")
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
            button(name, True)
            button(name, False)
            return {"ok": True}
        if c == "mode":
            to = cmd.get("to")
            if to not in ("media", "terminal"):
                return {"error": "No such mode"}
            toggle(to)
            if to == "media" and not media.active:
                return {"error": "There's no screen for media mode"}
            return {"ok": True}
        if not media.active:
            for n in list(held):
                key_up(n)
        return media.web_command(cmd)

    sel = selectors.DefaultSelector()
    pads = Pads(sel)
    media.pads = pads
    if control is not None:
        sel.register(control.r, selectors.EVENT_READ, "control")
    found(pads.scan(time.monotonic(), force=True), quiet=True)
    if media.boot_media:                          # Settings: open on the home screen
        media.boot_media = False
        media.enter()

    try:
        while not (stop and stop()):
            nxt = min([t for _, t in held.values()] + list(menu_held.values()) + list(pending.values())
                      + [pads.next_scan])
            timeout = max(0.0, nxt - time.monotonic())
            if media.active or media.proc or media.learn:
                timeout = min(timeout, media.tick_limit())

            for key, _ in sel.select(timeout):
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
                    pad_event(pad, ev)

            found(pads.scan(time.monotonic()))
            media.tick()
            learn_check()

            now = time.monotonic()
            for k, t in list(pending.items()):
                if now >= t:                          # SELECT or START alone: out it goes
                    del pending[k]
                    button(k[1], True, pads.by_path.get(k[0]))
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
        for pad in list(pads.by_path.values()) + list(pads.power.values()):
            pads.drop(pad)
        sel.close()


def main():
    keys = sorted({k for combo in TERMINAL.values() for k in combo})
    ui = UInput({e.EV_KEY: keys}, name=NAME)
    move_old_places()                              # (what it kept by its old name: where it keeps it now)
    media = Media()
    media.shrinker.start()                         # (big videos made smaller, in the background)
    media.updater.start()                          # (a newer version looked for now and then: System > Update software)
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
