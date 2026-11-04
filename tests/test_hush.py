"""The GPi Case's speaker in the terminal: with nothing playing it's given silence (aplay of /dev/zero), which stops
when music plays or media mode opens, starts again when the music ends, isn't tried again for a while if it won't
play, and is never started without the case."""
import io, json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
S = SP + "/t_hush"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480
    def show(self, img): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
started = []


class Silence:
    def __init__(self, cmd, stdin=None, **k):
        self.cmd, self.stdin_name, self.dead, self.ended = cmd, getattr(stdin, "name", None), False, False
        self.preexec = k.get("preexec_fn")
        started.append(self)
    def poll(self): return 0 if self.dead else None
    def terminate(self): self.dead = self.ended = True
    def wait(self, timeout=None): return 0
    def kill(self): self.dead = True


real_popen = subprocess.Popen
subprocess.Popen = lambda cmd, *a, **k: (Silence(cmd, **k) if cmd and cmd[0] == "aplay" else real_popen(cmd, *a, **k))
g.shutil.which = lambda name, *a, **k: "/usr/bin/" + name
g.sound_cards = lambda: [("vc4hdmi0", "HDMI 1"), ("Headphones", "Headphones")]

# ---- not a GPi Case: never
m = g.Media()
m.gpi_case = False
m.tick(); m.tick()
check("not a GPi Case: no silence in the terminal", not started)

# ---- a GPi Case
m = g.Media()
m.gpi_case = True
check("media mode not open yet: the terminal", not m.active)
m.tick()
check(f"in the terminal, nothing playing: silence for the case's speaker ({started and started[-1].cmd})",
      len(started) == 1 and started[0].cmd[:2] == ["aplay", "-q"] and "-D" in started[0].cmd
      and started[0].cmd[started[0].cmd.index("-D") + 1] == "default:CARD=Headphones"
      and started[0].stdin_name == "/dev/zero" and started[0].preexec is not None)
m.tick(); m.tick()
check("...just the one", len(started) == 1)

# music: it takes over
m.proc, m.kind = type("P", (), {"poll": lambda self: None, "stdin": io.StringIO()})(), "audio"
m.cur = {"title": "x", "kind": "audio", "src": "/x.mp3", "key": "x"}
m.started = time.monotonic()
m.tick()
check("music playing: the silence stops", started[0].ended and m.hush_proc is None)
m.tick()
check("...and doesn't start again while it plays", len(started) == 1)
m.proc.poll = lambda: 0                              # (the last song ends)
m.started = time.monotonic() - 100
m.queue, m.qi = [m.cur], 0
m.tick(); m.tick()
check("the music ends: silence again", len(started) == 2 and not started[1].dead)

# media mode
m.enter()
check("media mode opens: no silence there", started[1].ended and m.hush_proc is None)
m.tick(); m.tick()
check("...nor while it's open", len(started) == 2)
m.leave(); m.tick()
check("back to the terminal: silence again", len(started) == 3 and not started[2].dead)

# it won't play: not tried again straight away
started[2].dead = True
m.tick(); m.tick()
check(f"it stops by itself: not tried again straight away ({len(started)})", len(started) == 3 and m.hush_proc is None)
m.hush_wait = time.monotonic() - 1
m.tick()
check("...a minute later, it is", len(started) == 4)

# without the Headphones card: the system's own output
g.sound_cards = lambda: [("vc4hdmi0", "HDMI 1")]
m.hush_stop(); m.tick()
check("no Headphones card: the system's sound output", "-D" not in started[-1].cmd)

m.shutdown()
check("the app stops: so does the silence", started[-1].ended and m.hush_proc is None)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
