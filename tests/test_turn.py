"""A screen on its side (Settings > Rotate screen): the menus, turned 90, 180 or 270 degrees onto the screen's own
pixels, exactly as they'd be on a screen that lies wide (portrait screens: 400x1280 like a 7.9" one, 720x1280,
1080x1920, and 480x640 at 16 bits), quick paths and all (whole pixels doubled, a box at a time, straight into the
screen's memory or written row by row), the bars round a video, turned another way while it's up; the screen read
back for the web page, turned back; a game's pictures turned too (the real emulator playing a test game: its
pictures, its picture for the AI player and for its menu's background, a 3D game's frame from the graphics chip);
mplayer's video turned (and what it writes over it); the setting: the menus turned at once, the terminal too, a
game and a video as they start, and the row not there on the GPi Case's own screen."""
import io, os, shutil, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np
from PIL import Image, ImageDraw
from pitato import emulator as EMU, games as GM, library as L, screen as SC

S = SP + "/tturn"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u/Games/Saves")
os.makedirs(S + "/bin")
shutil.copy(SP + "/roms/nestest.nes", S + "/home/u/Games/nestest.nes")
open(f"{S}/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
for tool in ("chvt", "fgconsole"):
    open(f"{S}/bin/{tool}", "w").write("#!/bin/sh\necho 1\n")
for f in os.listdir(S + "/bin"):
    os.chmod(f"{S}/bin/{f}", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=10):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


RGB32 = [(16, 8), (8, 8), (0, 8)]
RGB16 = [(11, 5), (5, 6), (0, 5)]


def fake_fb(name, w, h, bpp, turn=0, stride=None, mapped=True):
    path = f"{S}/fb_{name}"
    stride = stride or w * bpp // 8
    open(path, "wb").write(b"\x77" * (stride * h))
    fb = object.__new__(g.Framebuffer)
    fb.f = open(path, "r+b", buffering=0)
    fb.turn = turn
    if not mapped:
        fb.mem = None                                   # (as if the screen couldn't be mapped: written row by row)
    fb.setup(w, h, 0, 0, bpp, fields_for(bpp), stride)
    return fb, path


def fields_for(bpp):
    return RGB16 if bpp == 16 else RGB32


def pixels(path, w, h, bpp, stride=None):
    stride = stride or w * bpp // 8
    a = np.frombuffer(open(path, "rb").read(), dtype="<u2" if bpp == 16 else "<u4")
    return a[:stride * h // (bpp // 8)].reshape(h, stride // (bpp // 8))[:, :w]


def menu_of(w, h, seed=1):
    """A menu picture: noise (so any pixel out of place shows), a red line along the top, a green corner."""
    rng = np.random.default_rng(seed)
    im = Image.fromarray(rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8), "RGB")
    dd = ImageDraw.Draw(im)
    dd.rectangle((0, 0, w - 1, 9), fill=(255, 0, 0))
    dd.rectangle((w - 10, h - 10, w - 1, h - 1), fill=(0, 255, 0))
    return im


# ---- the menus: turned onto a screen on its side, exactly as on one that lies wide -----------------------------
for (dw, dh, bpp) in ((480, 800, 32), (480, 800, 16), (720, 720, 32), (400, 1280, 32), (720, 1280, 32), (1080, 1920, 32),
                       (480, 640, 16)):
    for turn in (90, 180, 270):
        uw, uh = SC.turned(dw, dh, turn)
        for mapped in (True, False):
            tag = f"{dw}x{dh}_{bpp}_{turn}_{int(mapped)}"
            fb, path = fake_fb("t" + tag, dw, dh, bpp, turn, mapped=mapped)
            ref, rpath = fake_fb("r" + tag, uw, uh, bpp, 0, mapped=mapped)
            same = (fb.w, fb.h, fb.tw, fb.th, fb.ox, fb.oy, fb.real_w, fb.real_h) == \
                   (ref.w, ref.h, ref.tw, ref.th, ref.ox, ref.oy, ref.real_w, ref.real_h)
            img = menu_of(fb.w, fb.h, seed=turn)
            t0 = time.perf_counter()
            fb.show(img)
            took = (time.perf_counter() - t0) * 1000
            ref.show(img)
            got = SC.unturn_pixels(pixels(path, dw, dh, bpp), turn)
            want = pixels(rpath, uw, uh, bpp)
            box = (fb.w // 4, fb.h // 3, fb.w // 4 + 57, fb.h // 3 + 41)   # (a box drawn afresh: odd sizes)
            img2 = img.copy()
            ImageDraw.Draw(img2).rectangle(box, fill=(250, 200, 0))
            fb.show_part(img2, box)
            ref.show_part(img2, box)
            got2 = SC.unturn_pixels(pixels(path, dw, dh, bpp), turn)
            want2 = pixels(rpath, uw, uh, bpp)
            vbox = (fb.real_w // 5, 3, fb.real_w - fb.real_w // 5, fb.real_h - 7)
            fb.blank_outside(vbox)
            ref.blank_outside(vbox)
            got3 = SC.unturn_pixels(pixels(path, dw, dh, bpp), turn)
            want3 = pixels(rpath, uw, uh, bpp)
            if mapped or turn == 90:
                check(f"{dw}x{dh} ({bpp} bit), turned {turn}°{'' if mapped else ', written row by row'}: menus "
                      f"{fb.w}x{fb.h} on {fb.real_w}x{fb.real_h} as it's seen ({'whole pixels' if fb.sharp else 'scaled'},"
                      f" {took:.0f} ms), as on a screen that lies wide; a box drawn afresh; a video's bars",
                      same and np.array_equal(got, want) and np.array_equal(got2, want2)
                      and np.array_equal(got3, want3) and fb.memory() is (None if not mapped else fb.mem))
            else:
                check(f"...{dw}x{dh} turned {turn}°, written row by row", same and np.array_equal(got, want)
                      and np.array_equal(got2, want2) and np.array_equal(got3, want3))
            fb.close(); ref.close()

fb, path = fake_fb("w4", 480, 800, 32, 90)
check(f"Waveshare's 4\" 480x800, turned a quarter: the menus fill it, {fb.w}x{fb.h} on {fb.real_w}x{fb.real_h}, "
      f"one pixel each (not scaled)", (fb.w, fb.h, fb.tw, fb.th, fb.ox, fb.oy) == (800, 480, 800, 480, 0, 0)
      and fb.same)
fb.close()
fb, path = fake_fb("w4b", 480, 800, 32, 0)
check(f"...not turned: the menus small in its middle ({fb.tw}x{fb.th} at {fb.ox}, {fb.oy}), as before",
      (fb.tw, fb.th) == (480, 360))
fb.close()
# the top of the menus at the screen's own right edge (90°: a quarter clockwise), left (270°)
fb, path = fake_fb("edge90", 400, 1280, 32, 90)
fb.show(menu_of(fb.w, fb.h))
px = pixels(path, 400, 1280, 32)
red = 0xff0000
check(f"90°: the menus' top along the screen's own right edge (its top-left corner: {hex(px[fb.ox, 399])})",
      px[640, 399] == red and px[640, 0] != red)
fb.close()
fb, path = fake_fb("edge270", 400, 1280, 32, 270)
fb.show(menu_of(fb.w, fb.h))
px = pixels(path, 400, 1280, 32)
check("270°: ...along its left edge", px[640, 0] == red and px[640, 399] != red)
# turned another way while it's up
fb.turn_to(90)
check(f"turned another way while it's up: worked out afresh ({fb.real_w}x{fb.real_h}), the screen black first",
      (fb.real_w, fb.real_h) == (1280, 400) and not pixels(path, 400, 1280, 32).any())
fb.show(menu_of(fb.w, fb.h))
px = pixels(path, 400, 1280, 32)
check("...then the menus that way", px[640, 399] == red and px[640, 0] != red)
fb.turn_to(0)
check(f"...and back ({fb.real_w}x{fb.real_h})", (fb.real_w, fb.real_h) == (400, 1280) and fb.turn == 0)
fb.close()
SC.set_turn(0)
fb, path = fake_fb("plain", 640, 480, 16)
fb.show(menu_of(640, 480))
check("not turned: the GPi Case's screen written as ever (not mapped, the same pixels)", fb.memory() is None and
      fb.same and pixels(path, 640, 480, 16)[0, 0] == 31 << 11)
fb.close()

# ---- the screen read back (the web page): turned back -----------------------------------------------------------
fb, path = fake_fb("web", 400, 1280, 32, 90)
img = menu_of(fb.w, fb.h)
fb.show(img)
with open(path, "rb") as f:
    seen = SC.read_screen(f, (400, 1280, 0, 0, 32, RGB32, 1600), max_w=640, turn=90)
up = fb.last.resize((fb.tw, fb.th))
check(f"the screen read back for the web page: as it's seen ({seen.size}), the top red, the bottom right green",
      seen.size == (640, 200) and seen.getpixel((320, 1))[0] > 200 and seen.getpixel((320, 1))[1] < 60
      and seen.getpixel((320 + int(fb.tw / 4) - 3, 197))[1] > 200)
SC.set_turn(270)
check(f"...its size, as it's seen ({SC.turned(400, 1280)})", SC.turned(400, 1280) == (1280, 400))
SC.set_turn(45)
check("...a turn that isn't one: none", SC.TURN == 0)
fb.close()

# ---- a game: its pictures turned too ------------------------------------------------------------------------------
def screen_file(name, w, h, bits=32):
    path = f"{S}/game_{name}.bin"
    open(path, "wb").write(bytes(w * h * bits // 8))
    return path


def emu_screen(path, w, h, bits, turn):
    os.environ["PITATO_FB"] = f"{path}:{w}x{h}:{bits}"
    try:
        return EMU.Screen(turn=turn)
    finally:
        del os.environ["PITATO_FB"]


rng = np.random.default_rng(4)
frames = {"rgb565": (rng.integers(0, 65536, size=(160, 240), dtype=np.uint16), EMU.FMT_RGB565),
          "xrgb8888": (rng.integers(0, 1 << 24, size=(224, 256), dtype=np.uint32), EMU.FMT_XRGB8888)}
for (dw, dh, bits) in ((480, 800, 32), (720, 720, 32), (400, 1280, 32), (480, 640, 16), (1080, 1920, 32)):
    for turn in (90, 180, 270):
        uw, uh = SC.turned(dw, dh, turn)
        for mode in ("Fit", "Sharp", "Fill"):
            for kind, (frame, fmt) in frames.items():
                p1, p2 = screen_file(f"t{dw}{turn}", dw, dh, bits), screen_file(f"r{dw}{turn}", uw, uh, bits)
                s, r = emu_screen(p1, dw, dh, bits, turn), emu_screen(p2, uw, uh, bits, 0)
                s.mode = r.mode = mode
                s.show(frame, fmt, frame.shape[1] / frame.shape[0])
                r.show(frame, fmt, frame.shape[1] / frame.shape[0])
                got = SC.unturn_pixels(pixels(p1, dw, dh, bits), turn)
                want = pixels(p2, uw, uh, bits)
                s.shot(S + "/s.ppm"); r.shot(S + "/r.ppm")
                shots = open(S + "/s.ppm", "rb").read() == open(S + "/r.ppm", "rb").read()
                snaps = np.array_equal(np.asarray(s.snapshot()), np.asarray(r.snapshot()))
                ok = np.array_equal(got, want) and shots and snaps and (s.w, s.h) == (uw, uh)
                if not ok or (kind == "rgb565" and mode == "Fit"):
                    check(f"a game on {dw}x{dh} ({bits} bit) turned {turn}° ({mode}, {kind}): its pictures as on a "
                          f"screen that lies wide; its picture for the AI player and for its menu, as it's seen", ok)
                s.close(); r.close()


class FakeGPU:
    """What the graphics chip does: the frame, scaled to fill what it's read into (rows of row_px)."""
    def __init__(self, frame):
        self.frame = frame                              # (red, green, blue rows)

    def read(self, view, kind, row_px, w, h, flipped=True, smooth=True):
        dh, dw = view.shape
        ys = (np.arange(dh) * h // dh)
        xs = (np.arange(dw) * w // dw)
        rgb = self.frame[ys][:, xs]
        return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])


f3d = rng.integers(0, 256, size=(240, 320, 3), dtype=np.uint8)
for turn in (90, 180, 270):
    uw, uh = SC.turned(720, 1280, turn)
    p1, p2 = screen_file(f"g{turn}", 720, 1280), screen_file(f"gr{turn}", uw, uh)
    s, r = emu_screen(p1, 720, 1280, 32, turn), emu_screen(p2, uw, uh, 32, 0)
    s.show_gpu(FakeGPU(f3d), 320, 240, 4 / 3)
    r.show_gpu(FakeGPU(f3d), 320, 240, 4 / 3)
    check(f"a 3D game's frame from the graphics chip, turned {turn}°: as on a screen that lies wide",
          np.array_equal(SC.unturn_pixels(pixels(p1, 720, 1280, 32), turn), pixels(p2, uw, uh, 32)))
    s.close(); r.close()

# the real emulator, playing a test game: started turned
FBT, FBR = screen_file("realt", 480, 640, 16), screen_file("realr", 640, 480, 16)
shots = {}
for name, path, (w, h), turn in (("turned", FBT, (480, 640), 90), ("wide", FBR, (640, 480), 0)):
    os.environ["PITATO_FB"] = f"{path}:{w}x{h}:16"
    run = GM.GameRun({"path": S + "/home/u/Games/nestest.nes", "title": "nestest", "system": "nes"})
    run.start(GM.find_core("nes"), resume=False, turn=turn)
    started = run.wait_started(15)
    time.sleep(2.5)
    shots[name] = pixels(path, w, h, 16).copy()
    if name == "turned":
        args = run.p.args
    run.quit()
    until(lambda: run.ended, 10)
    del os.environ["PITATO_FB"]
check(f"the real emulator, told to turn its pictures ({' '.join(args[args.index('--turn'):args.index('--turn') + 2])}):"
      " the game as it'd be on a screen that lies wide", started and shots["wide"].any()
      and np.array_equal(SC.unturn_pixels(shots["turned"], 90), shots["wide"]))
os.environ["PITATO_FB"] = f"{FBT}:480x640:16"
SC.set_turn(90)
bg = EMU.screen_picture()
del os.environ["PITATO_FB"]
check(f"...the game's menu: its picture behind it, as it's seen ({bg.size if bg else None})", bg is not None
      and bg.size == (640, 480))
SC.set_turn(0)

# ---- a video: mplayer turns it ---------------------------------------------------------------------------------------
args = L.video_scale("Fit", None, 1280, 400, turn=90)
check(f"a video, turned 90°: scaled for the screen as it's seen, what's written over it put on, then turned ({args})",
      args == ["-vf", "dsize=1280:400:0,scale=0:0,expand=::::1,rotate=1"])
check("...270°: the other way; 180°: upside down", L.video_scale("Fit", None, 1280, 400, turn=270)[-1].endswith(
    ",expand=::::1,rotate=2") and L.video_scale("Fit", None, 1280, 400, turn=180)[-1].endswith(",expand=::::1,flip,mirror"))
full = L.video_scale("Full screen", (1920, 1080), 1280, 400, turn=90)
check(f"...Full screen and Stretch too ({full})", full == ["-vf", "scale=1280:720,crop=1280:400,expand=::::1,rotate=1"]
      and L.video_scale("Stretch", None, 1280, 400, turn=90) == ["-vf", "scale=1280:400,expand=::::1,rotate=1"])
check("...on a 640x480 screen as it's seen: the same way (not the GPi Case's own)",
      L.video_scale("Fit", None, 640, 480, turn=90) == ["-vf", "dsize=640:480:0,scale=0:0,expand=::::1,rotate=1"]
      and L.video_scale("Fit", None, 640, 480) == ["-zoom", "-xy", "640", "-vf", "scale"])
VID = S + "/v.mp4"
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25", "-t", "2",
                "-pix_fmt", "yuv420p", VID], check=True)
out = S + "/png"
os.makedirs(out, exist_ok=True)
subprocess.run(["mplayer", "-really-quiet", "-nosound", "-vo", f"png:outdir={out}", "-frames", "2", "-osdlevel", "3"]
               + L.video_scale("Fit", None, 1280, 400, turn=90) + [VID], stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL, timeout=60)
pngs = sorted(os.listdir(out))
im = Image.open(os.path.join(out, pngs[-1])).convert("RGB") if pngs else None
upright = im.transpose(Image.ROTATE_90) if im else None   # (turned back, as it's seen)
ref_dir = S + "/pngr"
os.makedirs(ref_dir, exist_ok=True)
subprocess.run(["mplayer", "-really-quiet", "-nosound", "-vo", f"png:outdir={ref_dir}", "-frames", "2"]
               + L.video_scale("Fit", None, 1280, 400) + [VID], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               timeout=60)
ref = Image.open(os.path.join(ref_dir, sorted(os.listdir(ref_dir))[-1])).convert("RGB")
diff = np.abs(np.asarray(upright, dtype=int)[60:, :] - np.asarray(ref, dtype=int)[60:, :]).mean() if im else 255
osd = np.abs(np.asarray(upright, dtype=int)[:40] - np.asarray(ref, dtype=int)[:40]).max() if im else 0
check(f"...the real mplayer: the picture turned ({im.size if im else None}: tall), as it's seen the same as on a screen "
      f"that lies wide (off by {diff:.2f} on average), where you are in it written over it before it's turned",
      im is not None and im.size == (400, 711) and diff < 2 and osd > 100)

# ---- turned while Game of Life's open (its pictures kept for the old size: made afresh) -------------------------
for full in ("Off", "On"):
    path = f"{S}/fb_live_{full}"
    open(path, "wb").write(bytes(480 * 800 * 4))
    live = object.__new__(g.Framebuffer)
    live.f = open(path, "r+b", buffering=0)
    live.turn = 0
    live.setup(480, 800, 0, 0, 32, RGB32, 480 * 4)
    real_fb = g.Framebuffer
    g.Framebuffer = lambda: live
    SC.FBCON_ROTATE = S + "/rotate_live"
    m = g.Media()
    m.state["settings"]["app_full"] = full
    m.enter()
    names = [t["name"] for t in g.LIBRARY]
    m.open_app(names.index("Game of Life"))
    for _ in range(3):
        m.dirty = True
        m.flush()
    m.open_app(names.index("Settings"))
    m.dirty = True
    m.flush()
    m.set_setting("turn", "90°")
    m.dirty = True
    m.flush()
    m.open_app(names.index("Game of Life"))
    err = None
    try:
        for _ in range(3):
            m.dirty = True
            m.flush()
    except Exception as ex:
        err = ex
    feet = [v.size for v in m.sim_feet.values()]
    check(f"turned while Game of Life's open (Full screen apps {full}): drawn afresh at the new size, no error "
          f"({m.sim_base[1].size if m.sim_base[1] else None}, its buttons {feet})", err is None and m.sim_base[1].size ==
          (800, 480) and all(w == 800 for w, _ in feet))
    m.set_setting("turn", "Off")
    m.leave()
    g.Framebuffer = real_fb
    SC.set_turn(0)
fb, path = fake_fb("odd", 480, 800, 32, 90)
fb.show(Image.new("RGB", (640, 480), (200, 0, 0)))
check("...a picture of the old size shown anyway: scaled to the new one, not an error",
      SC.unturn_pixels(pixels(path, 480, 800, 32), 90)[240, 400] == 200 << 16)
fb.close()

# ---- the setting ---------------------------------------------------------------------------------------------------
class FB:
    def __init__(self):
        self.w, self.h, self.last, self.turn, self.turns = 640, 480, None, SC.TURN, []
        self.real_w, self.real_h = SC.turned(640, 480, self.turn)

    def show(self, img):
        self.last = img

    def show_part(self, img, box):
        self.last = img

    def invalidate(self):
        pass

    def turn_to(self, turn):
        self.turns.append(turn)
        self.turn = turn

    def close(self):
        pass


ROT = S + "/rotate_all"
open(ROT, "w").write("0")
SC.FBCON_ROTATE = ROT
g.Framebuffer = FB
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
m.case = None
keys = [k for k, _, _ in m.settings_root_rows()]
check(f"Settings: Rotate screen, after Resolution's place ({keys[keys.index('turn') - 1:keys.index('turn') + 1]})",
      "turn" in keys and m.setting("turn") == "Off")
m.set_setting("turn", "90°")
check(f"...90°: everything drawn turned from now on ({SC.TURN}), the menus at once ({m.fb.turns}), the terminal too "
      f"({open(ROT).read()!r})", SC.TURN == 90 and m.fb.turns == [90] and open(ROT).read() == "1")
check(f"...a game, as it starts ({SC.screen_turn()}), and a video", SC.screen_turn() == 90 and
      m.video_args()[-1].endswith(",expand=::::1,rotate=1") and "rotate=1" in " ".join(m.video_args()))
m.set_setting("turn", "Off")
check(f"...Off: back ({SC.TURN}, {m.fb.turns}, {open(ROT).read()!r})", SC.TURN == 0 and m.fb.turns == [90, 0]
      and open(ROT).read() == "0" and "rotate" not in " ".join(m.video_args()))
m.case = "2w"
m.res_info = lambda: None
check("...not there on the GPi Case's own screen", "turn" not in [k for k, _, _ in m.settings_root_rows()])
m.state["settings"]["turn"] = "270°"
check("...unless it's turned already (to turn it back)", "turn" in [k for k, _, _ in m.settings_root_rows()])
m.res_info = lambda: ("1920x1080", ["1920x1080"])
m.state["settings"]["turn"] = "Off"
check("...or the GPi Case 2 is in its dock, on a TV", "turn" in [k for k, _, _ in m.settings_root_rows()])
m.save_state()
open(ROT, "w").write("0")
SC.set_turn(0)
m.state["settings"]["turn"] = "180°"
m.save_state()
m2 = g.Media()
check(f"started with it set: everything drawn turned from the start ({SC.TURN}), the terminal too "
      f"({open(ROT).read()!r})", SC.TURN == 180 and open(ROT).read() == "2")
m2.state["settings"]["turn"] = "Off"
m2.save_state()
open(ROT, "w").write("3")
SC.set_turn(0)
g.Media()
check(f"...set Off: the terminal left as it is (a turn of your own: {open(ROT).read()!r})", open(ROT).read() == "3"
      and SC.TURN == 0)

# ---- Apps' programs (cmatrix and the rest), on media mode's console: turned too --------------------------
import fcntl, struct, termios
master, slave = os.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 80, 0, 0))
g.PROG_TTY = os.ttyname(slave)
SEEN = S + "/prog_saw"
open(f"{S}/bin/cmatrix", "w").write(f'#!/bin/sh\ncat "{ROT}" > "{SEEN}"\nexec sleep 30\n')
os.chmod(f"{S}/bin/cmatrix", 0o755)
modes = []
m3 = g.Media(); m3.load_fonts(); m3.fb = FB(); m3.active = True
m3.prog_mode = lambda mode: modes.append((mode, open(ROT).read()))
SC.TERMINAL_TURNED = False
m3.state["settings"]["turn"] = "Off"
SC.set_turn(0)
open(ROT, "w").write("3")                       # (a turn of your own: fbcon=rotate on the kernel's line)
m3.prog_start("cmatrix")
until(lambda: os.path.exists(SEEN) and open(SEEN).read(), 5)
check(f"cmatrix with the screen not turned (and never turned here): the terminal left as it is ({open(SEEN).read()!r})",
      open(SEEN).read() == "3")
m3.prog_stop()
os.remove(SEEN)
m3.set_setting("turn", "90°")
open(ROT, "w").write("0")                       # (the menus up: media mode's console in graphics mode, which the
modes.clear()                                   #  kernel passes over: still unturned)
m3.prog_start("cmatrix")
until(lambda: os.path.exists(SEEN) and open(SEEN).read(), 5)
check(f"turned 90°: cmatrix's console turned too, once it's in text mode and before cmatrix starts (text mode with "
      f"{modes[0][1]!r}, cmatrix saw {open(SEEN).read()!r})", modes and modes[0] == (0, "0") and open(SEEN).read() == "1")
m3.prog_stop()
check(f"...stopped: media mode's console back in graphics mode ({modes[-1][0]})", modes[-1][0] == 1)
open(ROT, "w").write("0")
m3.leave()
check(f"back to the terminal: turned as the screen is ({open(ROT).read()!r})", open(ROT).read() == "1")
SC.set_turn(0)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
