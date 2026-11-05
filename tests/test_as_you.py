"""The players and games run as you, not root (pitato/asyou.py): as your home folder's owner (gpitest here), in its
own group and the audio, video and render ones (the machine's sound, screen and graphics chip) and no others, with no
new privileges (sudo can't take them up to root), at the priority they'd have given themselves. mplayer (a stand-in
that says who it is), the length of a song (ffprobe, a stand-in too), and a real game (the emulator, with a test core,
where there is one: tests/run.py --list): its saves and its emulator's own folder handed over first, what root left
in them too (links not followed), and what it saves yours. What a game leaves for media mode (the AI player's look
at the screen, a game's achievements) is read with care: not through a link, a pipe or a file too big, and a look
only as the game makes them (PPM). Your home folder root's, or Pietato not root: as root, as before. In a mount
namespace of its own: everything it makes is on a tmpfs at /srv there."""
import grp, io, json, os, pwd, shutil, subprocess, sys, threading, time

from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
if os.environ.get("ASYOU_NS") != "1":
    os.execvpe("unshare", ["unshare", "-m", sys.executable, os.path.abspath(__file__)], dict(os.environ, ASYOU_NS="1"))
subprocess.run(["mount", "--make-rprivate", "/"], check=True)
subprocess.run(["mount", "-t", "tmpfs", "-o", "mode=755", "tmpfs", "/srv"], check=True)

sys.path.insert(0, TESTS)
import pietato_all as g  # noqa: E402
import pitato.asyou as AY  # noqa: E402
import pitato.gameai as GA  # noqa: E402
import pitato.lengths as LN  # noqa: E402
from PIL import Image  # noqa: E402

T, USER = "/srv/asyou", "gpitest"
HOME = T + "/home"
OUT = T + "/out"
me = pwd.getpwnam(USER)
gid_of = {n: grp.getgrnam(n).gr_gid for n in ("audio", "video", "render") if n in {x.gr_name for x in grp.getgrall()}}
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=15.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


def read(path):
    try:
        return open(path).read()
    except OSError:
        return ""


def status(pid):
    """A process's own words for who it is: {Uid: [...], Groups: [...], NoNewPrivs: '1'}."""
    out = {}
    for line in read(f"/proc/{pid}/status").splitlines():
        k, _, v = line.partition(":")
        if k in ("Uid", "Gid", "Groups", "NoNewPrivs"):
            out[k] = v.split()
    return out


for d in (T + "/bin", HOME + "/Music", HOME + "/Games/Saves", HOME + "/Games/nes", OUT, T + "/media"):
    os.makedirs(d, exist_ok=True)
for d in (HOME, HOME + "/Music", HOME + "/Games", HOME + "/Games/Saves", HOME + "/Games/nes", OUT):
    os.chown(d, me.pw_uid, me.pw_gid)
os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
WHO = """{ echo "uid=$(id -u)"; echo "groups=$(id -G)"; grep -E '^NoNewPrivs' /proc/self/status; echo "home=$HOME"; } """
for name, body in {
    "mplayer": f"#!/bin/sh\n{WHO} > {OUT}/mplayer.txt\nexec cat > /dev/null\n",   # (it waits on its commands)
    "ffprobe": f"#!/bin/sh\n{WHO} > {OUT}/ffprobe.txt\necho 12.5\n",
    "aplay": "#!/bin/sh\nexec cat > /dev/null\n",
}.items():
    open(f"{T}/bin/{name}", "w").write(body)
    os.chmod(f"{T}/bin/{name}", 0o755)


def said(path):
    return dict(line.split("=", 1) if "=" in line else (line.split(":")[0], line.split(":")[1].strip())
                for line in read(path).splitlines() if line.strip())


# ---- who they run as ------------------------------------------------------------------------------------------
AY.AS_YOU = True                                  # (tests/paths.py keeps the other tests' as root)
pre, you = AY.as_you(HOME)
want_groups = sorted({me.pw_gid, *gid_of.values()} - {0})
check(f"as you: your home folder's owner, its group, and the audio, video and render groups, no others "
      f"({you.get('user')}, {you.get('group')}, {you.get('extra_groups')})",
      you.get("user") == me.pw_uid and you.get("group") == me.pw_gid and you.get("extra_groups") == want_groups
      and "audio" in gid_of and "video" in gid_of)
check(f"...your home and name, and no new privileges for it or what it starts ({pre})",
      you["env"]["HOME"] == HOME and you["env"]["USER"] == USER and you["env"]["LOGNAME"] == USER
      and (pre == [shutil.which("setpriv"), "--no-new-privs", "--"] if shutil.which("setpriv") else pre == []))
os.makedirs(T + "/roots")
check("...not when your home folder's root's, or Pietato isn't root, or it's turned off: as root, as before",
      AY.as_you(T + "/roots") == ([], {}) and AY.as_you(T + "/nowhere") == ([], {})
      and (setattr(AY, "AS_YOU", False) or AY.as_you(HOME) == ([], {})) and not setattr(AY, "AS_YOU", True))
real_euid = AY.os.geteuid
AY.os.geteuid = lambda: 1000
not_root = AY.as_you(HOME)
AY.os.geteuid = real_euid
check(f"...nor when Pietato isn't root ({not_root})", not_root == ([], {}))

# ---- mplayer, as Media mode starts it ----------------------------------------------------------------------------
g.STATE_FILE = T + "/media/state.json"; g.CACHE_DIR = T + "/media/cache"; g.PLEX_FILE = T + "/media/plex.json"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img
    def show_part(self, img, box): FB.last = img
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media()
m.enter()
song = HOME + "/Music/song.mp3"
open(song, "wb").write(b"ID3" + bytes(64))
os.chown(song, me.pw_uid, me.pw_gid)
m.play([g.item(song, "song", "audio", song)], 0)
got = until(lambda: "home=" in read(OUT + "/mplayer.txt"))
w = said(OUT + "/mplayer.txt")
pid = getattr(m.proc, "pid", None)
nice = os.getpriority(os.PRIO_PROCESS, pid) if pid else None
check(f"a song: mplayer as you ({w.get('uid')}), in your group and the audio, video and render ones "
      f"({w.get('groups')})", got and w.get("uid") == str(me.pw_uid)
      and sorted({int(x) for x in w.get("groups", "").split()}) == want_groups)
check(f"...no new privileges (sudo can't take it to root: {w.get('NoNewPrivs')}), at the priority it had as root "
      f"({nice}), your home its home", w.get("NoNewPrivs") == "1" and nice == g.PLAYER_NICE and w.get("home") == HOME)
m.stop()
check("...stopped as ever", until(lambda: m.proc is None or m.proc.poll() is not None, 5))

os.remove(OUT + "/mplayer.txt")
real_home = g.home_dir
g.home_dir = lambda: T + "/roots"
m.play([g.item(song, "song", "audio", song)], 0)
got = until(lambda: "home=" in read(OUT + "/mplayer.txt"))
w = said(OUT + "/mplayer.txt")
pid = getattr(m.proc, "pid", None)
check(f"your home folder root's: mplayer as root, as before ({w.get('uid')}, {os.getpriority(os.PRIO_PROCESS, pid)})",
      got and w.get("uid") == "0" and os.getpriority(os.PRIO_PROCESS, pid) == g.PLAYER_NICE)
m.stop()
g.home_dir = real_home

# ---- a song's length (ffprobe), as you too ---------------------------------------------------------------------------
clip = HOME + "/Music/clip.mka"
open(clip, "wb").write(b"\x1a\x45\xdf\xa3" + bytes(64))
os.chown(clip, me.pw_uid, me.pw_gid)
n = LN.probe_length(clip)
w = said(OUT + "/ffprobe.txt")
check(f"a song's length, asked of ffprobe as you ({n}, {w.get('uid')}, no new privileges: {w.get('NoNewPrivs')})",
      n == 12.5 and w.get("uid") == str(me.pw_uid) and w.get("NoNewPrivs") == "1")

# ---- handing a game's folders over --------------------------------------------------------------------------------
own = T + "/cache/games/psp"
os.makedirs(own + "/PSP/SAVEDATA")
open(own + "/ppsspp.ini", "w").write("[General]\n")
open(T + "/secret", "w").write("root's own\n")
os.symlink(T + "/secret", own + "/PSP/link")
AY.hand_over(own, you)
mine = [p for p in (own, own + "/PSP", own + "/PSP/SAVEDATA", own + "/ppsspp.ini")
        if os.lstat(p).st_uid == me.pw_uid]
check(f"a game's own folder handed over: it, and what root made in it, yours ({len(mine)} of 4); a link in it, not "
      f"followed (what it points at still root's)", len(mine) == 4 and os.lstat(own + "/PSP/link").st_uid == me.pw_uid
      and os.stat(T + "/secret").st_uid == 0)
AY.hand_over(T + "/cache/games/n64", you)
check("...made, if it isn't there", os.stat(T + "/cache/games/n64").st_uid == me.pw_uid)

# ---- what a game leaves for media mode, read with care ------------------------------------------------------------
R = AY.shm_path(f"pitato-asyou-{os.getpid()}.bin")
open(R, "wb").write(b"plain")
fifo = AY.shm_path(f"pitato-asyou-{os.getpid()}.fifo")
os.mkfifo(fifo)
link = AY.shm_path(f"pitato-asyou-{os.getpid()}.link")
os.symlink(T + "/secret", link)


def refused(path, most=1 << 20):
    try:
        AY.read_theirs(path, most)
    except OSError:
        return True
    return False


t0 = time.monotonic()
check(f"a file a game left: read ({AY.read_theirs(R)!r}); a link, a pipe, one too big: not (and no waiting on the "
      f"pipe: {time.monotonic() - t0:.2f} s)", AY.read_theirs(R) == b"plain" and refused(link) and refused(fifo)
      and refused(R, most=3) and time.monotonic() - t0 < 1 and R.startswith(("/dev/shm/", "/tmp/")))
for p in (R, fifo, link):
    os.remove(p)


class Run:
    ended, state = False, "on"
    def ask(self, line, what, wait):
        return "shot", "ok"


look = object.__new__(GA.GameIO)
look.run, look.ai = Run(), type("AI", (), {"stopping": threading.Event()})()
look.shot_path, look.shots_missed, look.shot_at = T + "/shot.ppm", 0, 0.0
buf = io.BytesIO()
Image.new("RGB", (8, 6), (200, 40, 40)).save(buf, "PPM")
open(look.shot_path, "wb").write(buf.getvalue())
seen = look.look()
buf = io.BytesIO()
Image.new("RGB", (8, 6), (200, 40, 40)).save(buf, "PNG")
open(look.shot_path, "wb").write(buf.getvalue())
not_ppm = look.look()
os.remove(look.shot_path)
os.symlink(T + "/secret", look.shot_path)
linked = look.look()
check(f"the AI player's look at the screen: a picture the game made (PPM) seen; anything else (a PNG, a link): not "
      f"({type(seen).__name__}, {not_ppm}, {linked})", isinstance(seen, GA.Look) and not_ppm is None and linked is None)

# ---- a real game (the emulator, with a test core where there's one) ---------------------------------------------------
CORE = SP + "/cheevos_test/testcore_libretro.so"
if not os.path.isfile(CORE):
    print("(no test core here: the game itself isn't played. tests/run.py --list says what it needs)", flush=True)
else:
    shutil.copy(CORE, T + "/testcore_libretro.so")
    FBF = T + "/fb.bin"
    open(FBF, "wb").write(bytes(640 * 480 * 2))
    os.chown(FBF, 0, gid_of["video"])
    os.chmod(FBF, 0o660)                              # (as /dev/fb0 is: root's, and the video group's)
    os.environ["PITATO_FB"] = f"{FBF}:640x480:16"
    rom = HOME + "/Games/nes/Test Game (USA).nes"
    open(rom, "wb").write(b"NES\x1a\x01\x01" + bytes(10) + bytes(range(256)) * 64)
    os.chown(rom, me.pw_uid, me.pw_gid)
    old = HOME + "/Games/Saves/Test Game (USA).srm"
    open(old, "wb").write(bytes(8192))                # (an older Pietato's save: root's)
    run = g.GameRun({"path": rom, "title": "Test Game", "system": "nes"})
    run.start(T + "/testcore_libretro.so", sound="", volume=80, picture="Fit", fb=FBF, resume=False, cheevos=False)
    on = until(lambda: run.state == "on" or run.ended, 20)
    st = status(run.p.pid)
    nice = os.getpriority(os.PRIO_PROCESS, run.p.pid)
    fds = [os.readlink(f"/proc/{run.p.pid}/fd/{n}") for n in os.listdir(f"/proc/{run.p.pid}/fd")]
    check(f"a game: the emulator as you ({st.get('Uid')}), your group and the audio, video and render ones "
          f"({st.get('Groups')}), the screen open as the video group may", on and run.state == "on"
          and st.get("Uid", [""])[:1] == [str(me.pw_uid)]
          and sorted({int(x) for x in st.get("Groups", [])}) == want_groups and FBF in fds)
    check(f"...no new privileges ({st.get('NoNewPrivs')}), and a little ahead of the rest, as it had as root ({nice})",
          st.get("NoNewPrivs") == ["1"] and nice == g.GAME_NICE)
    check("...an older save of root's handed over first", os.stat(old).st_uid == me.pw_uid)
    run.quit()
    until(lambda: run.ended, 15)
    saves = sorted(os.listdir(HOME + "/Games/Saves"))
    theirs = [n for n in saves if os.lstat(os.path.join(HOME + "/Games/Saves", n)).st_uid != me.pw_uid]
    check(f"...quit: where you were kept, yours ({saves}; not yours: {theirs})",
          any(n.endswith(".state.auto") for n in saves) and not theirs)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
