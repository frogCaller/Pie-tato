"""TV channels that stopped after a few seconds (the Waveshare's HDMI Pi Zero 2 W): what plays them now.
1) The Pi's HDMI sound goes straight to its IEC958 encoder (hdmi:), not through plug and softvol (default:). On a
   stand-in for the Pi's HDMI sound (an IEC958 encoder in front of a pretend card, with a converter in front of it
   as softvol is) and one moment of the sound running dry, as a late stream's makes it: the old way stops the real
   mplayer dead (the log's assertion, exit code 1), the new way plays on to the end.
2) Settings > Sound's choices: mplayer's -ao for each (the system's own, when that's the HDMI card, too).
3) HLS streams FFmpeg turns down for their pieces' links: the word that tells it not to mind goes only to an FFmpeg
   that knows it (the real mplayer here, given it, plays nothing); a channel turned down is played again with it.
4) A live channel that stops by itself after playing is tuned in again: three times in two minutes at most."""
import collections, io, json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import screen as scr, tv

S = SP + "/t_tvstops"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


# 1) the real mplayer, the old way and the new, on a stand-in for the Pi's HDMI sound -------------------------------
A = S + "/alsa"
os.makedirs(A + "/home")
open(A + "/home/.asoundrc", "w").write("""
# The Pi's HDMI sound as alsa-lib has it (cards/vc4-hdmi.conf, pcm/hdmi.conf), on a pretend card ("null"):
pcm.piiec {                     # hdmi.0: the IEC958 encoder, then the card
	type iec958
	slave { format IEC958_SUBFRAME_LE pcm "null" }
	status [ 0x04 0x82 0x00 0x01 ]
	hdmi_mode true
}
pcm.!default {                  # default: plug, something in front of the encoder (softvol, on the Pi), the encoder
	@args [ CARD ]
	@args.CARD { type string default "x" }
	type plug
	slave { pcm "piiec" format S32_LE }
}
pcm.!hdmi {                     # hdmi: straight to the encoder, its channel status as given
	@args [ CARD DEV AES0 AES1 AES2 AES3 ]
	@args.CARD { type string }
	@args.DEV { type integer }
	@args.AES0 { type integer default 0x04 }
	@args.AES1 { type integer default 0x82 }
	@args.AES2 { type integer default 0x00 }
	@args.AES3 { type integer default 0x02 }
	type iec958
	slave { format IEC958_SUBFRAME_LE pcm "null" }
	status [ $AES0 $AES1 $AES2 $AES3 ]
	hdmi_mode true
}
""")
shim = A + "/underrun_shim.so"
subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-o", shim, SP + "/hdmialsa/underrun_shim.c", "-ldl"], check=True)
tone = SP + "/hdmialsa/tone20.m4a"
if not os.path.exists(tone):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
                    "-ac", "2", "-c:a", "aac", tone], check=True)


def mplayer_with(ao):
    env = dict(os.environ, HOME=A + "/home", LD_PRELOAD=shim, FAKE_UNDERRUN_AT="40")
    r = subprocess.run(["mplayer", "-slave", "-quiet", "-novideo", "-softvol", "-volume", "50", "-ao", ao, tone],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=120)
    return r.returncode, r.stdout + r.stderr


old_ao = "alsa:device=default=vc4hdmi,alsa"                    # (what it was)
new_ao = scr.sound_device(None, "vc4hdmi")
rc, out = mplayer_with(old_ao)
check(f"the old way ({old_ao}): the sound running dry once stops mplayer dead, as in the log (exit {rc})",
      rc == 1 and "the sound ran dry" in out and "snd_pcm_plugin_status: Assertion" in out
      and "interrupted by signal 6" in out)
rc, out = mplayer_with(new_ao)
check(f"the new way ({new_ao}): it plays on to the end (exit {rc})",
      rc == 0 and "the sound ran dry" in out and "Assertion" not in out and "Exiting... (End of file)" in out
      and "using device hdmi:vc4hdmi,0,4,130,0,1" not in out)   # (-v not given: the device line isn't said)
env = dict(os.environ, HOME=A + "/home")
r = subprocess.run(["mplayer", "-v", "-slave", "-quiet", "-novideo", "-endpos", "1", "-ao", new_ao, tone],
                   stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=60)
check("mplayer reads it as hdmi:vc4hdmi,0,4,130,0,1 (the card, port 0, the channel status), and makes the sound "
      "16 bit itself", "alsa-init: using device hdmi:vc4hdmi,0,4,130,0,1" in r.stdout
      and "AO: [alsa] 44100Hz 2ch s16le" in r.stdout)

# 2) Settings > Sound's choices --------------------------------------------------------------------------------
files = {}
real_read = g.read_file
g.read_file = lambda p, *a, **k: files.get(p, "") if p.startswith(("/proc/asound", "/sys/class/drm")) else real_read(p, *a, **k)
own = S + "/alsaconf"
os.makedirs(own)
scr.ALSA_OWN = (own + "/asound.conf", own + "/conf.d/*.conf")
files["/proc/asound/cards"] = " 0 [vc4hdmi        ]: vc4-hdmi - vc4-hdmi\n                      vc4-hdmi\n"
check("HDMI, chosen: straight to its encoder", scr.sound_device(None, "vc4hdmi") == "alsa:device=hdmi=vc4hdmi.0.4.130.0.1,alsa")
check("a Pi 4's second HDMI port: its own card", scr.sound_device(None, "vc4hdmi1") == "alsa:device=hdmi=vc4hdmi1.0.4.130.0.1,alsa")
check("the system's own, which is the HDMI card (the kernel's first, nothing said otherwise): the same",
      scr.sound_device(None, "") == "alsa:device=hdmi=vc4hdmi.0.4.130.0.1,alsa")
open(own + "/asound.conf", "w").write("defaults.pcm.card 1\n")
check("...but not when /etc/asound.conf says which: plain alsa", scr.sound_device(None, "") == "alsa")
os.remove(own + "/asound.conf"); os.makedirs(own + "/conf.d")
open(own + "/conf.d/99-pipewire-default.conf", "w").write("pcm.!default { type pipewire }\n")
check("...nor when a conf.d file names a default (PipeWire's)", scr.sound_device(None, "") == "alsa")
shutil.rmtree(own + "/conf.d")
os.environ["ALSA_CARD"] = "Headphones"
check("...nor with ALSA_CARD set", scr.sound_device(None, "") == "alsa")
del os.environ["ALSA_CARD"]
files["/proc/asound/cards"] = " 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones\n 1 [vc4hdmi        ]: vc4-hdmi - vc4-hdmi\n"
check("the system's own, the Headphones first (the GPi Case): plain alsa, as it was", scr.sound_device(None, "") == "alsa")
check("Headphones, chosen: as it was", scr.sound_device(None, "Headphones") == "alsa:device=default=Headphones,alsa")
check("a USB speaker: as it was", scr.sound_device(None, "Device") == "alsa:device=default=Device,alsa")
check("Bluetooth: as it was", scr.sound_device(None, "bluetooth") == "alsa:device=bluealsa,alsa")
check("aplay (the bot's voice, games, the GPi's quiet): as it was",
      scr.aplay_device(None, "vc4hdmi") == "default:CARD=vc4hdmi" and scr.aplay_device(None, "") == "")
check("not an HDMI card that only starts like one", scr.sound_device(None, "vc4hdmix") == "alsa:device=default=vc4hdmix,alsa")

# 3) HLS streams FFmpeg turns down ---------------------------------------------------------------------------
L = S + "/libs"
os.makedirs(L + "/a"); os.makedirs(L + "/b")
open(L + "/a/libavformat.so.61.7.100", "wb").write(b"\x7fELF" + b"\0" * 100 + b"live_start_index\0extension_picky\0max_reload\0")
open(L + "/b/libavformat.so.59.27.100", "wb").write(b"\x7fELF" + b"\0" * 100 + b"live_start_index\0allowed_extensions\0")
os.symlink("libavformat.so.61.7.100", L + "/a/libavformat.so.61")
open(L + "/empty.so", "wb").close()
real_libs = tv.LAVF_LIBS


def knows(pats):
    tv._lavf_knows.clear(); tv.LAVF_LIBS = pats
    return tv.lavf_knows("extension_picky")


check("a newer FFmpeg (it has the word): told", knows((L + "/a/libavformat.so.*",)) and tv.hls_lenient() == ["-lavfdopts", "o=extension_picky=0"])
check("an older one: not told", not knows((L + "/b/libavformat.so.*",)) and tv.hls_lenient() == [])
check("one of each here (mplayer's could be either): not told", not knows((L + "/a/libavformat.so.*", L + "/b/libavformat.so.*")))
check("no libavformat at all, or an empty file: not told", not knows((L + "/none/libavformat.so.*",)) and not knows((L + "/empty.so",)))
check("this machine's own (FFmpeg 6.1, Ubuntu's): not told", not knows(real_libs))
pyav = sorted(__import__("glob").glob(SP + "/pyav/site/av.libs/libavformat-*.so.*"))
if pyav:
    check("FFmpeg 8 (PyAV's libavformat): told", knows((pyav[0],)))
tv.LAVF_LIBS = real_libs; tv._lavf_knows.clear()
check("what FFmpeg says turning one down is seen, and nothing else",
      tv.hls_turned_down(["[hls @ 0x55]URL https://x/mf2/640x360_800000?u=a.ts&d=46 is not in allowed_segment_extensions"])
      and tv.hls_turned_down(["detected format mpegts extension none mismatches allowed extensions in url https://x/y"])
      and not tv.hls_turned_down(["Exiting... (End of file)", "[aac @ 0x1]Prediction is not allowed in AAC-LC."]))

# the player: what it's given, and what happens when one's turned down
procs = []


class FakeProc:
    def __init__(self, args, **k):
        self.args = list(args); self.rc = None
        self.stdin = io.StringIO(); self.stdout = io.StringIO(""); self.stderr = io.StringIO("")
        procs.append(self)

    def poll(self): return self.rc
    def wait(self, timeout=None): return 0
    def kill(self): self.rc = -9
    def terminate(self): self.rc = -15


g.subprocess.Popen = FakeProc
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()


class FB:
    w, h = 640, 480
    real_w, real_h = 800, 480
    def show(self, img): pass
    def show_part(self, img, box): pass
    def invalidate(self): pass
    def blank_outside(self, box): pass
    def close(self): pass


g.Framebuffer = FB
g.hls_pick = lambda url, timeout=8: url.replace("master.m3u8", "640x360/index.m3u8")
waits = []
m = g.Media(); m.enter()
real_wait = m.render_wait
m.render_wait = lambda title, status, **k: (waits.append((title, status)), real_wait(title, status, **k))[1]
chan = g.item("stream:https://cdn.example/live/master.m3u8", "Free Channel", "live", "https://cdn.example/live/master.m3u8")
other = g.item("stream:https://cdn.example/two/master.m3u8", "Other Channel", "live", "https://cdn.example/two/master.m3u8")
q = [chan, other]
lenient = ["-lavfdopts", "o=extension_picky=0"]


def has_lenient(args):
    return any(args[k:k + 2] == lenient for k in range(len(args) - 1))


tv._lavf_knows["extension_picky"] = True
m.play(q, 0)
p = procs[-1]
check("a live HLS channel, a newer FFmpeg: told not to mind its pieces' links (the version picked, as before)",
      has_lenient(p.args) and p.args[-1] == "ffmpeg://https://cdn.example/live/640x360/index.m3u8")
tv._lavf_knows["extension_picky"] = False
m.play(q, 0)
p = procs[-1]
check("...an older FFmpeg: not (it'd play nothing)", not has_lenient(p.args))
radio = g.item("https://radio.example/hls/master.m3u8", "Radio", "radio", "https://radio.example/hls/master.m3u8")
tv._lavf_knows["extension_picky"] = True
m.play([radio], 0, show=False)
check("radio: never (mplayer plays it its own way)", not has_lenient(procs[-1].args))
open(S + "/home/u/clip.mp4", "wb").write(b"x")
m.play([g.item(S + "/home/u/clip.mp4", "clip", "video", S + "/home/u/clip.mp4")], 0)
check("a video file: never", not has_lenient(procs[-1].args))
m.stop()

# turned down at once, an FFmpeg not seen to know the word: played again at once, told; and later ones told too
tv._lavf_knows["extension_picky"] = False
m.view = "list"; m.play(q, 0)
p = procs[-1]
p.said.extend(["[hls @ 0xaa]URL https://stream-us-east-1.example.com/mf2/640x360_800000?u=x.ts&d=46 is not in "
               "allowed_segment_extensions", "LAVF_header: av_open_input_stream() failed", "Exiting... (End of file)"])
p.rc = 0
m.started = time.monotonic() - 4.0
n = len(procs)
m.tick()
check("turned down for its pieces' links: played again at once, told not to mind",
      len(procs) == n + 1 and has_lenient(procs[-1].args) and procs[-1].args[-1] == p.args[-1]
      and m.proc is procs[-1] and m.kind == "live" and m.msg is None)
check("...and the FFmpeg's now known to know it", tv.lavf_knows("extension_picky"))
p = procs[-1]
p.said.extend(["Exiting... (End of file)"]); p.rc = 0
m.started = time.monotonic() - 3.0
m.tick()
check("told, and it still won't: no more tries, it says so, back to the list",
      len(procs) == n + 1 and m.proc is None and m.msg == "Couldn't play that stream" and m.view == "list")
tv._lavf_knows["extension_picky"] = False
m.msg = None; m.view = "list"; m.play(q, 0)
p = procs[-1]; p.said.extend(["[aac @ 0x1]Prediction is not allowed in AAC-LC.", "Exiting... (End of file)"]); p.rc = 1
m.started = time.monotonic() - 2.0
n = len(procs)
m.tick()
check("one that won't play for another reason: not tried again (as before)",
      len(procs) == n and m.msg == "Couldn't play that stream" and m.view == "list")

# 4) a live channel that stops by itself after playing ----------------------------------------------------------
m.msg = None; m.view = "list"; waits.clear()
m.play(q, 0)
starts = len(procs)
for k in range(3):
    p = procs[-1]
    p.said.extend(["mplayer: pcm_plugin.c:572: snd_pcm_plugin_status: Assertion failed.",
                   "MPlayer interrupted by signal 6 in module: play_audio"])
    p.rc = 1
    m.started = time.monotonic() - 40.0
    m.tick()
check("stopped by itself after playing a while: tuned in again, three times, 'Reconnecting' on the screen",
      len(procs) == starts + 3 and m.proc is procs[-1] and m.kind == "live" and m.cur is chan
      and [w for w in waits if w[1] == "Reconnecting"] == [("Free Channel", "Reconnecting")] * 3
      and procs[-1].args[-1] == procs[starts - 1].args[-1])
p = procs[-1]; p.rc = 1
m.started = time.monotonic() - 40.0
m.tick()
check("a fourth time in two minutes: let go, saying so, back to the list",
      len(procs) == starts + 3 and m.proc is None and m.view == "list"
      and m.msg == "That channel keeps stopping. Try it again later")
m.msg = None
m.play(q, 1)
p = procs[-1]; p.rc = 0; m.started = time.monotonic() - 30.0
n = len(procs)
m.tick()
check("another channel's stops don't count against it", len(procs) == n + 1 and m.cur is other)
m.stop()
m.live_stops = [(k, t - 200) for k, t in m.live_stops]
m.play(q, 0)
p = procs[-1]; p.rc = 0; m.started = time.monotonic() - 30.0
n = len(procs)
m.tick()
check("two minutes on, the first channel's tuned in again too", len(procs) == n + 1 and m.cur is chan)
m.stop()
m.play(q, 0)
p = procs[-1]; p.rc = 1; m.started = time.monotonic() - 3.0
n = len(procs)
m.tick()
check("one that stops at once isn't tuned in again over and over: it says it couldn't play it (as before)",
      len(procs) == n and m.msg == "Couldn't play that stream" and m.view == "list")
m.msg = None
m.play(q, 0)
m.stop()
check("B (stopped on purpose): nothing tuned in again", m.proc is None and m.kind is None)
m.active = False
m.play(q, 0)
p = procs[-1]; p.rc = 0; m.started = time.monotonic() - 30.0
n = len(procs)
m.tick()
check("media mode not up: not tuned in again", len(procs) == n and m.proc is None)
print("ALL OK" if all(ok_all) else "SOME FAILED")
