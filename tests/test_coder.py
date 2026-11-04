"""The Bot at work (the Coder, before it was part of the Bot): its clock (holds, one-off gestures, stuck,
naps), its sounds and clips (through a fake aplay), WAVs, its page and buttons, left and right between
chatting and work, the toast elsewhere, the web page's ways in, and the control server's routes."""
import io, json, math, os, shutil, socket, struct, sys, threading, time, wave, http.client
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tcoder"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/bin")
LOG = S + "/aplay.log"
with open(S + "/bin/aplay", "w") as f:            # a fake aplay: notes what it was given, takes as long as it'd play
    f.write("""#!/usr/bin/env python3
import sys, time, json, os, array
args = sys.argv[1:]
data = sys.stdin.buffer.read()
rate = int(args[args.index("-r") + 1]); ch = int(args[args.index("-c") + 1])
a = array.array("h"); a.frombytes(data[:len(data) // 2 * 2])
with open(os.environ["FAKE_APLAY_LOG"], "a") as f:
    f.write(json.dumps({"args": args, "bytes": len(data), "peak": max((abs(x) for x in a), default=0)}) + "\\n")
time.sleep(len(data) / (2 * ch * rate))
""")
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["FAKE_APLAY_LOG"] = LOG
try:
    import evdev  # noqa: F401  (the Pi's Python here has a stand-in on its path)
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.PLEX_FILE = S + "/plex.json"; g.CACHE_DIR = S + "/cache"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def wait_for(c, t=5.0):
    e = time.time() + t
    while time.time() < e:
        if c():
            return True
        time.sleep(0.02)
    return c()


def plays():
    try:
        return [json.loads(x) for x in open(LOG)]
    except OSError:
        return []


def clear_plays():
    open(LOG, "w").close()


def wav(secs=0.6, rate=22050, ch=1, bits=16, loud_from=0.2, fmt_tag=1, data_size=None):
    n = int(secs * rate)
    samples = []
    for i in range(n):
        t = i / rate
        v = int(12000 * math.sin(2 * math.pi * 220 * t)) if t >= loud_from else 0
        samples += [v] * ch
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    if bits == 8:
        pcm = bytes((s >> 8) + 128 & 255 for s in samples)
    block = ch * bits // 8
    if fmt_tag == 0xFFFE:                         # WAVE_FORMAT_EXTENSIBLE
        fmt = struct.pack("<HHIIHHHHI", 0xFFFE, ch, rate, rate * block, block, bits, 22, bits, 0) \
            + struct.pack("<H", 1) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
    else:
        fmt = struct.pack("<HHIIHH", fmt_tag, ch, rate, rate * block, block, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"LIST" + struct.pack("<I", 4) + b"INFO"           # a chunk to skip
    body += b"data" + struct.pack("<I", len(pcm) if data_size is None else data_size) + pcm
    return b"RIFF" + struct.pack("<I", len(body)) + body


class FB:
    w, h = 640, 480
    same = True
    def __init__(self):
        self.last, self.frames, self.whole, self.parts = None, 0, 0, []
    def show(self, img):
        self.last = img.copy(); self.frames += 1; self.whole += 1
    def show_part(self, img, box):
        self.last = img.copy(); self.frames += 1; self.parts.append(tuple(box))
    def close(self):
        pass


# the clock, quicker (the poses' own movements keep their timing)
g.CODER_HOLD = 0.3
g.CODER_ONCE.update({"done": 0.5, "hello": 0.6, "shrug": 0.5, "wake": 0.6, "sleep": 0.5})
g.CODER_WAIT.update({"attention": 0.8, "error": 0.8})
g.CODER_STUCK = 1.0
g.CODER_NAP = 1.2
g.CODER_SOUND_AT.update({"done": 0.1, "hello": 0.05, "attention": 0.05, "error": 0.05, "shrug": 0.05})

m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
co = m.coder
ci = m.tab_index("friend")

# ---- where it lives: in the Bot, with the Coder's icon
names = [n for n, _ in m.home_apps()]
check(f"no Coder on the home screen, the Bot instead: {names}", "Coder" not in names and "Bot" in names)
check("no Coder tab", all(t["type"] != "coder" and t["name"] != "Coder" for t in g.LIBRARY))
ic = g.draw_icon("Bot", 84)
px = ic.getpixel((42, 6))
check(f"the Bot's icon: its head, on a tile in its colour (orange: {px[:3]})", ic.size == (84, 84)
      and "Coder" not in g.HOME_ICONS and px[3] == 255 and px[0] > px[1] > px[2])
app = next(a for a in m.web_catalog()["apps"] if a["name"] == "Bot")
check(f"...and on the web page's apps: {app}", app["about"] == "Does what you ask, and chats with you"
      and not any(a["name"] == "Coder" for a in m.web_catalog()["apps"]))
check("its sound is on to start with, and the Bot starts out chatting", m.setting("coder_sound") == "On"
      and m.bot_mode() == "chat")

# ---- its clock
check("it starts at rest", co.current() == "rest" and not co.asleep)
s = co.snapshot(time.monotonic())
check(f"no agent yet: {m.coder_status(s)}", m.coder_status(s) == ("Waiting for your coding agent", "START shows how to connect it"))
time.sleep(g.CODER_HOLD + 0.05)
check("an agent says typing", co.ask("typing") == "typing" and co.heard > 0)
check("reading right after: typing has its moment first", co.ask("reading") == "typing")
check("...thinking too: the last one asked for waits", co.ask("thinking") == "typing" and co.pending == "thinking")
check("then it's the last one", wait_for(lambda: co.anim == "thinking", 1.0))   # (its own clock, nobody asking)
since = co.since
time.sleep(0.4)
co.ask("thinking")
check("the same again: it carries on (not started over)", co.since == since and co.pending is None)
time.sleep(0.4)
co.ask("done")
check("done: the bell", co.current() == "done" and co.done and co.work_from is None)
s = co.snapshot(time.monotonic())
title, sub = m.coder_status(s)
check(f"its desk says so: {title!r} {sub!r}", title == "Done" and sub.startswith("at "))
check("...then it rests", wait_for(lambda: co.anim == "rest", 1.5) and co.done)
check("its desk still says done", m.coder_status(co.snapshot(time.monotonic()))[0] == "Done")

co.ask("typing")
check("busy without a word for too long: it asks for you", wait_for(lambda: co.anim == "attention", 2.5))
check("...for a while, then rests", wait_for(lambda: co.anim == "rest", 2.0))
check("nothing happening: it nods off", wait_for(lambda: co.anim == "sleep", 2.5))
check("...and sleeps (asked, it says it's resting)", wait_for(lambda: co.asleep and co.anim == "rest", 1.5)
      and co.current() == "rest")
title = m.coder_status(co.snapshot(time.monotonic()))[0]
check(f"its desk: {title}", title == "Asleep")
co.ask("rest"); co.ask("sleep")
check("rest or sleep while it's asleep: it sleeps on", co.asleep and co.anim == "rest" and co.pending is None)
co.ask("reading")
check("an agent at work again: it wakes", wait_for(lambda: co.anim == "reading", 1.0) and not co.asleep)
g.CODER_NAP = 600                                  # (no more naps from here on)
time.sleep(g.CODER_HOLD + 0.05)

# ---- sounds (a fake aplay)
m.set_setting("coder_sound", "On")
m.volume = 50
clear_plays()
co.ask("done")
check("the bell rings", wait_for(lambda: len(plays()) == 1, 3.0))
p = plays()[0] if plays() else {"args": [], "bytes": 0, "peak": 0}
full = max(abs(x) for x in struct.unpack(f"<{len(g.coder_sound('done')) // 2}h", g.coder_sound("done")))
check(f"...its own sound at the media volume: {p['args']} peak {p['peak']} of {full}",
      p["args"][p["args"].index("-r") + 1] == "22050" and p["args"][p["args"].index("-c") + 1] == "1"
      and p["bytes"] == len(g.coder_sound("done")) and abs(p["peak"] - full * 0.5) < full * 0.02)
check("...through the sound output from Settings", ("-D" in p["args"]) == bool(g.aplay_device(m.setting("sound"))))
wait_for(lambda: co.anim == "rest", 2)
time.sleep(0.4)
for name in ("hello", "attention", "error", "shrug"):
    pcm = g.coder_sound(name)
    check(f"a sound for {name}: {len(pcm) / 2 / 22050:.2f} s", 0.3 < len(pcm) / 2 / 22050 < 2.0)
check("no sound for typing", g.coder_sound("typing") == b"")
clear_plays()
m.set_setting("coder_sound", "Off")
co.ask("done")
time.sleep(0.8)
check("its sounds off: quiet", plays() == [])
m.set_setting("coder_sound", "On")
wait_for(lambda: co.anim == "rest", 2)
time.sleep(0.35)
m.proc = object()                                   # something playing
co.ask("done")
time.sleep(0.8)
check("something playing: quiet", plays() == [])
m.proc = None
wait_for(lambda: co.anim == "rest", 2)
time.sleep(0.35)
m.active = False                                    # the terminal, not media mode
co.ask("done")
check("not even in media mode: the bell still rings", wait_for(lambda: len(plays()) == 1, 3.0))
m.active = True
wait_for(lambda: co.anim == "rest", 2)
time.sleep(0.35)

wait_for(lambda: not co.speaker.locked(), 3)
clear_plays()
co.ask("attention")
since = co.since
time.sleep(g.CODER_HOLD + 0.1)
co.ask("attention")
same = co.since == since
dbg = (co.anim, co.pending, round(co.since - since, 3))
time.sleep(0.6)
check(f"it needs you, said twice: it carries on, with one call ({len(plays())} {dbg})", same and len(plays()) == 1)
wait_for(lambda: co.anim == "rest", 3)
time.sleep(0.35)

# ---- clips
check("WAV: mono", g.coder_wav(wav())[1:] == (22050, 1))
check("WAV: stereo 44.1k", g.coder_wav(wav(0.2, 44100, 2))[1:] == (44100, 2))
check("WAV: extensible", g.coder_wav(wav(0.2, fmt_tag=0xFFFE))[1:] == (22050, 1))
check("WAV: written as it streamed (data size 0)", len(g.coder_wav(wav(0.2, data_size=0))[0]) == int(0.2 * 22050) * 2)
for bad, why in ((b"hello", "not a WAV file"), (wav(0.2, bits=8), "expected 16-bit PCM, mono or stereo, 8000 to 48000 Hz"),
                 (wav(0.2)[:12 + 24], "no audio data"), (wav(0.2, rate=96000), "expected 16-bit PCM, mono or stereo, 8000 to 48000 Hz"),
                 (b"RIFF\x04\x00\x00\x00WAVE", "not a WAV file"), (wav(0.0), "no audio data")):
    try:
        g.coder_wav(bad)
        got = "fine"
    except ValueError as ex:
        got = str(ex)
    check(f"a bad WAV: {got!r}", got == why)
env = g.coder_envelope(*g.coder_wav(wav(0.6, loud_from=0.3)))
check(f"how loud, every 40 ms: quiet then loud ({len(env)})", len(env) == 15 and max(env[:6]) < 0.05 and min(env[9:]) > 0.9)

wait_for(lambda: not co.speaker.locked(), 3)          # (the bell before has finished)
clear_plays()
co.ask("typing")
time.sleep(g.CODER_HOLD + 0.05)
out = {}
th = threading.Thread(target=lambda: out.update(r=m.coder_say(wav(0.8), "talking")))
t0 = time.time()
th.start()
check("a clip: it talks", wait_for(lambda: co.anim == "talking", 1.0))
energies = []
for _ in range(20):
    energies.append(co.snapshot(time.monotonic())["energy"])
    time.sleep(0.03)
check(f"...its mouth follows it: {min(energies):.2f} to {max(energies):.2f}", max(energies) > 0.8 and min(energies) < 0.1)
co.ask("done")
check("an agent asks for something meanwhile: it waits for the clip", co.anim == "talking" and co.pending == "done")
th.join(5)
took = time.time() - t0
check(f"answered once said: {out.get('r')} after {took:.2f} s", out.get("r") == (200, {"ok": True, "ms": 800})
      and 0.75 < took < 1.4)
p = plays()
check(f"...out loud: {p and p[0]['args']}", len(p) == 1 and p[0]["bytes"] == int(0.8 * 22050) * 2)
check("then what was asked for", co.anim == "done")
wait_for(lambda: co.anim == "rest", 2)
time.sleep(0.35)
wait_for(lambda: not co.speaker.locked(), 3)          # (the bell has finished)
co.ask("reading")
time.sleep(g.CODER_HOLD + 0.05)
before = (co.anim, co.pending)
r = m.coder_say(wav(0.3), "thinking")
check(f"a clip while thinking, then back to what it was busy with: {r} {before} -> {co.anim} {co.pending}", r[0] == 200 and co.anim == "reading")
m.set_setting("coder_sound", "Off")
clear_plays()
t0 = time.time()
r = m.coder_say(wav(0.5), "talking")
check(f"its sounds off: it mouths it, taking as long ({time.time() - t0:.2f} s)", r[0] == 200 and plays() == []
      and 0.45 < time.time() - t0 < 1.0)
m.set_setting("coder_sound", "On")
check("a clip in a pose with a sound of its own: no", m.coder_say(wav(0.2), "done") ==
      (400, {"ok": False, "error": "a clip is said talking, typing, reading, thinking or rest"}))
check("not a WAV: no", m.coder_say(b"nope", "talking") == (415, {"ok": False, "error": "not a WAV file"}))
clear_plays()
outs = []
ths = [threading.Thread(target=lambda: outs.append(m.coder_say(wav(0.4, 16000), "talking"))) for _ in range(2)]
t0 = time.time()
for t in ths:
    t.start()
for t in ths:
    t.join(5)
p = plays()
check(f"two clips at once take turns ({time.time() - t0:.2f} s)", len(outs) == 2 and time.time() - t0 > 0.75
      and len(p) == 2 and p[0]["args"][p[0]["args"].index("-r") + 1] == "16000")
voice_speaking = m.voice.speaking
th = threading.Thread(target=lambda: m.coder_say(wav(0.5), "talking"))
th.start()
wait_for(lambda: co.talking(), 1)
ok, why = m.say_aloud("hello")
check(f"the bot keeps quiet while the coder talks: {why!r}", not ok and why == "Not while your coding agent is talking")
th.join(5)

# ---- its page: the Bot, at work
m.set_setting("bot_mode", "work")
m.tab, m.view = ci, "list"
m.load_tab(ci)
check("the Bot at work: its page", m.on_coder_page() and m.on_bot_page() and not m.on_friend_page())
m.status_sig = m.status_signature()
m.fb = FB()
m.dirty = True; m.flush()
check("its page draws", m.fb.last is not None and m.fb.whole == 1)
for name in g.CODER_POSES:
    for t in (0.05, 0.4, 1.0, 2.5, 65):
        with co.cv:
            co.anim, co.since, co.asleep = name, time.monotonic() - t, False
        m.dirty = True; m.flush()
check("every pose draws, at every point", True)
with co.cv:
    co.anim, co.since, co.asleep = "rest", time.monotonic(), True
m.dirty = True; m.flush()
fb = m.fb
n0, w0 = len(fb.parts), fb.whole
for k in range(5):
    time.sleep(0.05)
    m.dirty = True; m.flush()
check(f"frame to frame, only the coder goes to the screen ({len(fb.parts) - n0} parts)", len(fb.parts) - n0 == 5
      and fb.whole == w0 and fb.parts[-1] == g.CO_DIRTY)
m.toast("Hello there", 2)
m.flush()
check("a toast: the whole picture", fb.whole == w0 + 1)
time.sleep(0.6)
m.dirty = True; m.flush()
check("...and after a pause too", fb.whole == w0 + 2)
m.msg = None

# the real screen: just that part is written
class F:
    def __init__(self): self.n, self.at = 0, []
    def seek(self, p): self.at.append(p)
    def write(self, b): self.n += len(b)
real = g.Framebuffer.__new__(g.Framebuffer)
real.f = F()
real.setup(640, 480, 0, 0, 16, [(11, 5), (5, 6), (0, 5)], 1280)
img = Image.new("RGB", (640, 480), (10, 20, 30))
real.show(img)
real.f.n = 0
real.show_part(img, g.CO_DIRTY)
x0, y0, x1, y1 = g.CO_DIRTY
check(f"on a 640x480 screen a part is just its rows ({real.f.n} bytes)", real.f.n == (x1 - x0) * (y1 - y0) * 2 and real.last is img)
tv = g.Framebuffer.__new__(g.Framebuffer)
tv.f = F()
tv.setup(1920, 1080, 0, 0, 32, [(16, 8), (8, 8), (0, 8)], 1920 * 4)
wide = Image.new("RGB", (tv.w, tv.h), (10, 20, 30))
tv.show(wide)
tv.f.n = 0
tv.show_part(wide, g.CO_DIRTY)
import math
kx, ky = tv.tw / tv.w, tv.th / tv.h
part = (x1 - x0) * (y1 - y0) * 4 * 4                    # (doubled each way)
check(f"on a 1080p TV (menus {tv.w}x{tv.h}, doubled) just that part too ({tv.f.n} bytes of {tv.tw * tv.th * 4})",
      tv.f.n == part and (tv.w, tv.h) == (960, 540) and tv.last is wide)
tv.f.n = 0
tv.show_part(img, g.CO_DIRTY)
check("...a picture of another size: the whole of it, scaled", tv.f.n == tv.tw * tv.th * 4)

# ticks: frames on time
m.fb = FB()
m.coder_next = 0
m.dirty = False
m.tick()
check(f"on its page the loop ticks quickly ({m.tick_limit()}), and a frame is due", m.tick_limit() == 0.1 and m.dirty)
m.dirty = False
m.tick()
check("...not again at once", not m.dirty)

# buttons
with co.cv:
    co.anim, co.since, co.asleep, co.pending = "rest", time.monotonic() - 5, False, None
heard = co.heard
hints = m.coder_hints(co.snapshot(time.monotonic()))
check(f"its buttons, left and right first: {[k + ' ' + l for k, l, *_ in hints]}",
      [(k, l) for k, l, *_ in hints] == [("◀▶", "Chat"), ("A", "Prompt"), ("Y", "Ring"), ("X", "Sound"), ("START", "Connect")])
m.msg = None
m.press("a")
check(f"A: a prompt for your agent, once it listens ({m.msg!r})", m.view == "list" and "isn't listening" in (m.msg or "")
      and co.anim == "rest" and co.heard == heard)
m.prompts.asked = time.monotonic()                 # (as if your agent had just asked for prompts)
m.press("a")
check("...it listens: a box to type it in", m.view == "keys" and m.kb["title"] == "A prompt for your coding agent")
m.press("b")
m.prompts.asked = -1e9
m.press("y")
check("Y rings the bell", co.anim == "done")
wait_for(lambda: co.anim == "rest", 2)
time.sleep(0.35)
co.ask("attention")
s = co.snapshot(time.monotonic())
check(f"it needs you: Y says OK ({m.coder_hints(s)[2]})", m.coder_hints(s)[2] == ("Y", "OK"))
time.sleep(g.CODER_HOLD + 0.05)
m.press("y")
check("...and it rests", co.anim == "rest")
m.press("x")
check(f"X turns its sounds off: {m.msg!r}", m.setting("coder_sound") == "Off" and m.msg == "Its sounds are off")
m.dirty = True; m.flush()
m.press("x")
check("...and on", m.setting("coder_sound") == "On")
m.volume = 60
m.press("up")
check(f"up: louder ({m.msg})", m.volume == 65 and m.msg == "Volume 65")
m.press("down"); m.press("down")
check("down: quieter", m.volume == 55)
m.dirty = True; m.flush()
lab = m.fb.last.crop((16, g.Media.LIST_TOP + 16, 196, g.Media.LIST_TOP + 42))
check("top left: its pages, Work lit", len(lab.getcolors(4096) or []) > 4 and g.ACCENT in lab.getdata()
      and lab.getpixel((14, 13)) != g.ACCENT)
m.press("start")
check("START: how to connect an agent", m.coder_help)
m.dirty = True; m.flush()
m.fb.last.save(SP + "/coder_help.png")
hints = m.coder_hints(co.snapshot(time.monotonic()))
check(f"...B closes it ({hints})", hints == [("B", "Close")])
m.press("b")
check("...closed, still on its page", not m.coder_help and m.view == "list" and m.tab == ci)
m.press("start")
m.press("left")
check("left and right do nothing while the card is up", m.coder_help and m.bot_mode() == "work")
m.press("b")
m.press("b")
check("B: home", m.view == "home")
m.view = "list"
m.press("r")
check("R: the next tab", m.tab != ci)
m.tab = ci
# left and right: chatting, and back to work (kept for next time)
m.press("left")
check(f"left: the Bot chats ({m.bot_mode()})", m.bot_mode() == "chat" and m.on_friend_page() and not m.on_coder_page()
      and m.setting("bot_mode") == "chat")
m.dirty = True; m.flush()
chat_shot = m.fb.last
lab = chat_shot.crop((16, g.Media.LIST_TOP + 16, 196, g.Media.LIST_TOP + 42))
check("...top left: its pages, Chat lit", len(lab.getcolors(4096) or []) > 4 and g.ACCENT in lab.getdata()
      and lab.tobytes() != m.fb.last.crop((16, 0, 196, 26)).tobytes())
m.press("right")
check("right: back at work", m.bot_mode() == "work" and m.on_coder_page())
m.press("right")
check("...and right again: still at work (the last of its pages)", m.bot_mode() == "work")
m.press("left"); m.press("left")
check("...left, left: Today, then", m.bot_mode() == "today")
m.press("right"); m.press("right")
check("...right, right: work", m.bot_mode() == "work")
m2 = g.Media()
check("kept for next time", m2.bot_mode() == "work")
m.set_setting("bot_mode", "chat")
co.ask("typing")
time.sleep(g.CODER_HOLD + 0.05)
co.ask("typing")
check(f"while it chats, a word on your agent: {m.bot_work_line()}", m.bot_work_line() == ("Your agent is typing", g.ACCENT))
m.dirty = True; m.flush()
from PIL import ImageChops
check("...on the chat page", m.fb.last is not None and ImageChops.difference(m.fb.last, chat_shot).getbbox() is not None)
m.set_setting("bot_mode", "work")
# a busy loop: everything fits along the bottom
from PIL import ImageDraw
d = ImageDraw.Draw(Image.new("RGB", (640, 480)))
for anim in ("rest", "attention"):
    hints = m.coder_hints({"anim": anim})
    w = 20 + sum(m.key_w(d, k) + 7 + d.textlength(l, font=m.fonts["small"]) + 18 for k, l, *_ in hints) - 18
    check(f"its hints fit ({anim}: {w:.0f} px)", w <= 620)

# a word about it elsewhere (chatting on the Bot is elsewhere too)
m.set_setting("bot_mode", "chat")
m.msg = None
wait_for(lambda: co.anim == "typing", 1)
time.sleep(g.CODER_HOLD + 0.05)
co.ask("attention")
check(f"chatting on the Bot: {m.msg!r}", m.msg == "Your coding agent needs you")
time.sleep(g.CODER_HOLD + 0.05)
m.set_setting("bot_mode", "work")
m.tab = m.tab_index("weather")
m.view = "list"
m.msg = None
co.ask("attention")
check(f"elsewhere in media mode: {m.msg!r}", m.msg == "Your coding agent needs you")
time.sleep(g.CODER_HOLD + 0.05)
m.msg = None
co.ask("done")
check(f"...{m.msg!r}", m.msg == "Your coding agent is done")
wait_for(lambda: co.anim == "rest", 2)
time.sleep(0.35)
m.tab = ci
m.msg = None
co.ask("done")
check("on its own page: no toast", m.msg is None)
wait_for(lambda: co.anim == "rest", 2)
time.sleep(0.35)
m.tick()
check("an agent has been heard: no more how-to on its desk", m.setting("coder_seen") == "yes")

# ---- the web page's ways in
m.set_setting("bot_mode", "chat")
m.view = "home"
check("the web page's apps, as they were: Coder opens the Bot at work",
      m.web_command({"cmd": "open", "app": "Coder"}) == {"ok": True} and m.on_coder_page())
check("Show it at work", m.web_friend_do({"do": "work"}) == {"ok": True} and m.on_coder_page())
check("Show on the Pi: chatting", m.web_friend_do({"do": "open"}) == {"ok": True} and m.on_friend_page())
w = m.web_friend()["work"]
check(f"the web page's Bot: your agent, at work: {w}", w["heard"] and w["title"] and not w["showing"]
      and w["pose"] in g.CODER_POSES)
m.set_setting("bot_mode", "work")
m.tab = ci

# ---- the control server: answered at once, off the main loop (nothing runs it here)
key = "k3y"
port = 5491
srv = g.serve_control(m, g.Control(), port=port, key=key)


def http_req(method, path, body=None, ctype="application/json", k=key):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"X-Pitato-Key": k}
    if body is not None:
        h["Content-Type"] = ctype
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


time.sleep(0.35)
st, r = http_req("POST", "/coder", json.dumps({"pose": "typing"}))
check(f"POST /coder: {st} {r}", st == 200 and r == {"ok": True, "pose": "typing"})
st, r = http_req("GET", "/coder")
check(f"GET /coder: {r}", r == {"ok": True, "pose": "typing"})
st, r = http_req("POST", "/coder", json.dumps({"pose": "dance"}))
check(f"a pose it doesn't know: {r}", r == {"ok": False, "error": "no such pose"})
st, r = http_req("POST", "/coder", json.dumps({"pose": "dead"}))
check(f"...like the one it doesn't have any more: {r}", r == {"ok": False, "error": "no such pose"})
t0 = time.time()
st, r = http_req("POST", "/coder/say?pose=talking", wav(0.5), "audio/wav")
check(f"POST /coder/say: {st} {r} after {time.time() - t0:.2f} s", st == 200 and r == {"ok": True, "ms": 500}
      and time.time() - t0 > 0.45)
st, r = http_req("POST", "/coder/say", b"not a wav", "audio/wav")
check(f"...not a WAV: {st} {r}", st == 415 and r["error"] == "not a WAV file")
st, r = http_req("POST", "/coder/say?pose=done", wav(0.2), "audio/wav")
check(f"...a pose it can't say a clip in: {st}", st == 400)
c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
c.putrequest("POST", "/coder/say"); c.putheader("X-Pitato-Key", key); c.putheader("Content-Length", str(g.CODER_CLIP_MAX + 1))
c.endheaders()
rr = c.getresponse()
check(f"...too big: {rr.status}", rr.status == 413)
st, r = http_req("POST", "/coder", json.dumps({"pose": "done"}), k="wrong")
check(f"without the key: {st}", st == 401)
srv.shutdown()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
