"""Files > Other computers, against real servers on this machine: SSH (sshd, sshfs) and Samba (smbd, smbclient).
This kernel has no CIFS, so 'mount -t cifs' is a stand-in (fakebin/mount) that opens the test share's folder
read-only (a bind mount) once it's checked the login it was given. The core (pitato/computers.py), the Files list
on the Pi's screen, and the web page's Computers tab (webui.py, through the real control server)."""
import atexit, io, json, os, shutil, socket, stat, subprocess, sys, threading, time, urllib.parse
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
os.environ["PATH"] = SP + "/fakebin:" + os.environ["PATH"]
sys.path.insert(0, TESTS)
sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_computers"
PW = "Op3n Sesame!"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def port_open(p):
    s = socket.socket(); s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", p)) == 0
    finally:
        s.close()


def procs():
    """The processes here: [(pid, its parent's, its command line)] (each found by what it is, not by a name)."""
    out = []
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            ppid = int(open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()[1])
            argv = [a.decode(errors="replace") for a in open(f"/proc/{p}/cmdline", "rb").read().split(b"\0") if a]
        except (OSError, ValueError, IndexError):
            continue
        out.append((int(p), ppid, argv))
    return out


def sshfs_of(where, port):
    """The sshfs that opened where (the folder in its command line), and the ssh it talks through (to that port, with
    this test's own known_hosts file: sshfs started it, then went on in the background without it)."""
    fs = [pid for pid, _, argv in procs() if argv[:1] == ["sshfs"] and where in argv]
    return fs, [pid for pid, _, argv in procs() if argv[:1] == ["ssh"] and f"-oPort={port}" in argv
                and f"-oUserKnownHostsFile={g.KNOWN_HOSTS}" in argv]


started = not any(port_open(p) for p in (445, 4445, 2222, 2223))
if started:                               # (this machine's own sshd and Samba, just for this; stopped at the end)
    atexit.register(lambda: subprocess.run(["bash", SP + "/net_servers.sh", "stop"], capture_output=True))
    subprocess.run(["bash", SP + "/net_servers.sh"], capture_output=True)
    D = SP + "/netsrv"
    if not port_open(4445) and os.path.exists(D + "/smb_win.conf"):
        subprocess.run(["smbd", "-s", D + "/smb_win.conf", "-D"]); time.sleep(1.5)
if not all(port_open(p) for p in (445, 4445, 2222, 2223)):
    print("FAIL the test servers didn't start (sshd, smbd: openssh-server and samba, with sshfs and smbclient)")
    sys.exit(1)

for w in sorted(g.mounted(S), reverse=True):
    subprocess.run(["umount", "-l", w])
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u/Videos")
open(S + "/home/u/Videos/mine.mp4", "wb").write(b"x" * 10)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"; g.KNOWN_HOSTS = S + "/known_hosts"
g.SECRETS = S + "/run"
open(g.STATE_FILE, "w").write('{"settings": {"start": "Terminal"}}')
g.home_dir = lambda: S + "/home/u"
import gk_static; gk_static.use_home(g, S + "/home/u")
real_run = subprocess.run
FAKE = {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd", "aplay", "systemctl"}


def fake_run(cmd, *a, **k):
    if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in FAKE:
        return type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
    return real_run(cmd, *a, **k)


subprocess.run = fake_run
CIFS_LOG = SP + "/out/fake_cifs.log"
open(CIFS_LOG, "w").close()


def cifs_log():
    return [l.strip() for l in open(CIFS_LOG) if l.strip()]


def mounts():
    return sorted(g.mounted(S + "/net"))


# ======== the core ==============================================================================
P = g.parse
check("addresses as typed", P("192.168.1.20") == {"host": "192.168.1.20", "port": 0, "how": "", "user": "", "share": ""}
      and P(r"\\pc\Media")["share"] == "Media" and P("smb://pc/Media")["how"] == "smb"
      and P("ssh://me@pc:2222") == {"host": "pc", "port": 2222, "how": "ssh", "user": "me", "share": ""}
      and P("me@pc")["how"] == "ssh" and P("pc:2222")["how"] == "ssh" and P("pc:445")["how"] == "smb"
      and P("[fe80::1]:22")["host"] == "fe80::1" and P(" pc.local. ")["host"] == "pc.local")
bad = []
for t in ("", "bad host!", "a b", "pc:99999", "http://x y"):
    try:
        P(t); bad.append(t)
    except g.Trouble as ex:
        if ex.kind != "typo":
            bad.append(t)
check(f"not addresses: said so ({bad})", not bad)
check("folder names", g.folder_name("192.168.1.20") == "192.168.1.20" and g.folder_name("pc:2222") == "pc_2222"
      and g.folder_name("[fe80::1]:22") == "fe80__1__22")

C = g.Computers()


def trouble(f, *a):
    try:
        f(*a)
        return None
    except g.Trouble as ex:
        return ex.kind


t0 = time.time()
check("SSH with no user name: asks for one", trouble(C.add, "127.0.0.1:2222") == "login")
check("...a wrong password: said so", trouble(C.add, "127.0.0.1:2222", "alice", "nope") == "bad_login")
check("...a computer that takes keys only: said so", trouble(C.add, "127.0.0.1:2223", "alice", PW) == "keys")
check("...one not answering on that port", trouble(C.add, "ssh://127.0.0.1:2299", "alice", "x") == "unreachable")
check(f"...no folders left behind by those: {os.listdir(S + '/net') if os.path.isdir(S + '/net') else []}",
      not os.path.isdir(S + "/net") or os.listdir(S + "/net") == [])
addr, (how, start) = C.add("127.0.0.1:2222", "alice", PW)
home = S + "/net/127.0.0.1_2222/home/alice"
check(f"SSH: added, starts in the user's own folder ({start})", addr == "127.0.0.1:2222" and how == "path" and start == home
      and "notes.txt" in os.listdir(start))
check("...read-only", subprocess.call(["touch", home + "/x"], stderr=subprocess.DEVNULL) != 0
      and not os.path.exists("/home/alice/x"))
saved = json.load(open(g.COMPUTERS_FILE))
check("saved, only root can read it", stat.S_IMODE(os.stat(g.COMPUTERS_FILE).st_mode) == 0o600
      and saved[0]["password"] == PW and saved[0]["home"] == "home/alice")
def key_kept(host):
    return real_run(["ssh-keygen", "-F", host, "-f", g.KNOWN_HOSTS], capture_output=True).returncode == 0


check("its SSH key kept", key_kept("[127.0.0.1]:2222"))
check("no login files left about", not [f for f in os.listdir(g.SECRETS) if f.startswith(".login-")])
check("nothing answering at all", trouble(C.add, "10.255.255.1") == "unreachable")
check("there, but sharing nothing", trouble(C.add, "127.0.0.2") == "nothing")
check("a name that isn't there", trouble(C.add, "nosuch.invalid") == "unknown")

# shared folders: a Samba that lists them to anyone (445), and one that's like Windows (4445)
addr, (how, shares) = C.add("127.0.0.1")
check(f"shared folders listed, not Windows' own C$ ({shares})", how == "shares" and shares == ["Media", "Public"])
check("Windows-like: asks for a login", trouble(C.add, "smb://127.0.0.1:4445") == "login")
check("...a wrong password", trouble(C.add, "smb://127.0.0.1:4445", "alice", "nope") == "bad_login")
check("...a user it doesn't know", trouble(C.add, "smb://127.0.0.1:4445", "bob", "x") == "bad_login")
r = C.add("smb://127.0.0.1:4445", "WORKGROUP\\alice", PW)
check(f"...right, with a domain too: {r}", r == ("127.0.0.1:4445", ("shares", ["Media", "Public"])))
where = C.open("127.0.0.1", "Public")
check("a guest share opens without a login", where == S + "/net/127.0.0.1/Public" and where in mounts()
      and "a song.mp3" in os.listdir(where))
log = cifs_log()[-1]
check(f"...read-only, as a guest ({log})", ",ro," in "," + log.split("opts=")[1].split(" ")[0] + "," and ",guest" in log)
check("a share that wants alice: asks", trouble(C.open, "127.0.0.1", "Media") == "login")
check("...its empty folder gone again", not os.path.exists(S + "/net/127.0.0.1/Media"))
C.sign_in("127.0.0.1", "alice", PW)
check("signing in closes what was open (to open again with it)", where not in mounts())
where = C.open("127.0.0.1", "Media")
log = cifs_log()[-1]
check(f"...then it opens, the login in a file only root reads ({log[-40:]})",
      where in mounts() and "user=alice" in log and "credmode=600" in log and "Films" in os.listdir(where))
check("...that file gone after", not [f for f in os.listdir(g.SECRETS) if f.startswith(".login-")])
os.environ["FAKE_CIFS_OLD"] = "1"
C.close(C.get("127.0.0.1"))
where = C.open("127.0.0.1", "Public")
del os.environ["FAKE_CIFS_OLD"]
check("an old computer: the older ways of talking tried", where in mounts() and "vers=1.0" in cifs_log()[-1]
      and "vers=2.0" in cifs_log()[-2])
check("a share that isn't there", trouble(C.open, "127.0.0.1", "Nope") == "noshare")
check("which computer a folder's on", C.owner(where + "/x")[0]["addr"] == "127.0.0.1" and C.owner(where)[1] == "Public"
      and C.is_top(where) and not C.is_top(where + "/x") and C.is_top(S + "/net/127.0.0.1_2222")
      and C.owner("/etc") is None)
subprocess.run(["umount", "-l", where]); subprocess.run(["umount", "-l", S + "/net/127.0.0.1_2222"])
C.ensure(where + "/sub")
C.ensure(home + "/Videos")
check("after a restart (nothing open), a folder on one opens again by itself",
      where in mounts() and S + "/net/127.0.0.1_2222" in mounts())
# a dropped connection: sshfs signs in again by itself; a dead one (its sshfs gone) is opened again
fs, ssh = sshfs_of(S + "/net/127.0.0.1_2222", 2222)
for pid in ssh:
    os.kill(pid, 9)
time.sleep(1)
check(f"a dropped SSH connection: back by itself ({len(ssh)} dropped)",
      ssh and sorted(os.listdir(home + "/My Photos")) == ["red.jpg"])
fs, _ = sshfs_of(S + "/net/127.0.0.1_2222", 2222)
check(f"...its sshfs found ({len(fs)})", len(fs) == 1)
for pid in fs:
    os.kill(pid, 9)
time.sleep(1)
check("...its sshfs gone: dead (but still listed as open)", not g.alive(S + "/net/127.0.0.1_2222")
      and S + "/net/127.0.0.1_2222" in mounts())
C.ensure(home + "/Videos")
check("...opened again when it's next wanted", g.alive(S + "/net/127.0.0.1_2222") and os.listdir(home + "/Videos") == ["clip.mp4"])
C.forget("127.0.0.1:2222")
check("forgetting closes it and its key", S + "/net/127.0.0.1_2222" not in mounts()
      and not os.path.exists(S + "/net/127.0.0.1_2222") and not key_kept("[127.0.0.1]:2222")
      and C.get("127.0.0.1:2222") is None)
C.close_all()
check("all closed when Pitato stops", mounts() == [])
for a in [c["addr"] for c in C.rows()]:
    C.forget(a)

# ======== the Pi's screen: Files ================================================================
g.list_devices = lambda: []


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    last = None

    def show(self, img):
        FB.last = img.copy()

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media()
m.enter()
bi = m.tab_index("browser")
m.tab = bi; m.view = "list"; m.load_tab(bi)


def settle(t=40):
    end = time.time() + t
    while time.time() < end:
        m.tick()
        if m.net_busy is None and not m.net_done:
            break
        time.sleep(0.05)
    m.tick()
    m.flush()


def rows():
    return [(it["title"], it["kind"]) for it in m.tab_items()]


def pick(title):
    i = [r[0] for r in rows()].index(title)
    m.sels[bi] = i
    return i


def press(name):
    m.press(name)
    m.flush()


def typed(text):
    m.kb["text"] = text
    m.close_keyboard(True)


check(f"home: Other computers at the top, the first folder picked ({rows()[:3]})",
      rows()[1] == ("Other computers", "netroot") and m.sels[bi] == 2)
pick("Other computers"); press("a"); settle()
check("Other computers: just Add a computer", rows() == [("..", "up"), ("Add a computer", "netadd")] and m.cwd == "net:")
pick("Add a computer"); press("a")
check("A: its address asked for, on the number row", m.view == "keys" and m.kb["title"].startswith("Computer's address")
      and m.kb["r"] == 0)
typed("127.0.0.1:2222"); settle()
check("SSH: a user name asked for", m.kb and m.kb["title"] == "User name on 127.0.0.1:2222")
typed("alice")
check("...then the password", m.kb and m.kb["title"] == "Password for alice")
typed("nope"); settle()
check(f"a wrong one: said so, and asked again ({m.msg})", m.msg == "That user name or password didn't work"
      and m.kb and m.kb["title"] == "User name on 127.0.0.1:2222" and m.kb["text"] == "alice")
typed("alice"); typed(PW); settle()
check(f"right: its files, from the user's own folder ({m.cwd})", m.cwd == home and m.view == "list"
      and ("notes.txt", "text") in rows() and ("Videos", "dir") in rows())
check("hidden files hidden", not any(t.startswith(".") and t != ".." for t, _ in rows()))
m.dirty = True; m.flush()
shot = FB.last.copy()
check("the place on top says the computer", m.net_place(m.cwd) == "127.0.0.1:2222  ›  /home/alice")
pick("Videos"); press("a"); settle()
check("into a folder on it", m.cwd == home + "/Videos" and ("clip.mp4", "video") in rows())
press("b"); settle()
check("B: up, the folder you came from picked", m.cwd == home and m.tab_items()[m.sels[bi]]["title"] == "Videos")
press("b"); settle(); press("b"); settle()
check("up to the computer's /", m.cwd == S + "/net/127.0.0.1_2222" and m.net_place(m.cwd) == "127.0.0.1:2222  ›  /")
press("b"); settle()
check("B from its /: Other computers, with it on the list", m.cwd == "net:"
      and rows() == [("..", "up"), ("127.0.0.1:2222", "netpc"), ("Add a computer", "netadd")])
hints = dict(m.list_hints())
check(f"hints there: Forget ({hints})", hints.get("Y") == "Forget" and hints.get("B") == "Up")
pick("127.0.0.1:2222"); press("a"); settle()
check("A on it: straight back into its files", m.cwd == home)

# a slow computer never holds the screen up
real_scan = g.scan
g.scan = lambda path: (time.sleep(3), real_scan(path))[1]
m.net_seen.clear()
pick("Videos"); t = time.time(); press("a"); took = time.time() - t
check(f"opening a slow folder: the screen goes on ({took:.2f}s)", took < 0.5 and m.net_busy is not None)
m.dirty = True; m.flush()
check("...the list says it's loading", m.net_busy["label"] == "Loading…")
loading_shot = FB.last.copy()
t = time.time(); press("b"); took = time.time() - t
check(f"...B works meanwhile ({took:.2f}s)", took < 0.5 and m.cwd == home)
settle()
check("...and the slow answer doesn't move you", m.cwd == home)
g.scan = real_scan

# no trips to the computer while the list is drawn (no counting what's in each folder)
real_listdir, real_getsize = os.listdir, os.path.getsize
trips = []
os.listdir = lambda p=".": (trips.append(p), real_listdir(p))[1]
os.path.getsize = lambda p: (trips.append(p), real_getsize(p))[1]
for _ in range(3):
    m.dirty = True; m.flush()
os.listdir, os.path.getsize = real_listdir, real_getsize
check(f"drawing the list asks the computer nothing ({trips[:2]})", not [p for p in trips if str(p).startswith(S + "/net")])

# shared folders
press("b"); settle(); press("b"); settle(); press("b"); settle()
pick("Add a computer"); press("a"); typed(r"\\127.0.0.1"); settle()
check(f"shared folders: listed straight away (guests may look) ({rows()})", m.cwd == "net:127.0.0.1"
      and rows() == [("..", "up"), ("Media", "netshare"), ("Public", "netshare")])
check("...the place on top", m.net_place(m.cwd) == "Other computers  ›  127.0.0.1")
pick("Public"); press("a"); settle()
check("a guest one opens", m.cwd == S + "/net/127.0.0.1/Public" and rows() == [("..", "up"), ("a song.mp3", "audio")])
check("...its place", m.net_place(m.cwd) == "127.0.0.1  ›  Public")
press("b"); settle()
check("B from a share's top: its computer's shares, it picked", m.cwd == "net:127.0.0.1"
      and m.tab_items()[m.sels[bi]]["title"] == "Public")
pick("Media"); press("a"); settle()
check("one that wants a login: asked", m.kb and m.kb["title"] == "User name on 127.0.0.1")
typed("alice"); typed("wrong"); settle()
check("...a wrong one: asked again", m.msg == "That user name or password didn't work" and m.kb
      and m.kb["text"] == "alice")
typed("alice"); typed(PW); settle(); settle()
check(f"...right: signed in and opened ({m.cwd})", m.cwd == S + "/net/127.0.0.1/Media" and ("Films", "dir") in rows()
      and m.msg == "Signed in")
pick("Films"); press("a"); settle()
check("into it", rows() == [("..", "up"), ("movie.mkv", "video")])
pic = home + "/My Photos/red.jpg"
check("no deleting a picture on another computer", (m.open_photo([pic], 0) or True)
      and (m.photo_delete() or True) and "can't be deleted" in m.msg and os.path.exists(pic))
m.close_viewer(); m.view = "list"

# a computer gone quiet: its file isn't opened, and the screen waits on it no more than a moment
real_stat = os.stat
os.stat = lambda p, *a, **k: (time.sleep(6) if str(p).startswith(S + "/net/") else None, real_stat(p, *a, **k))[1]
m.browse(home)
items = [dict(g.item(home + "/notes.txt", "notes.txt", "text", home + "/notes.txt"))]
t = time.time(); m.open_item(items, 0); took = time.time() - t
os.stat = real_stat
check(f"a quiet computer's file: not opened, the screen held up {took:.1f}s at most", took < 3
      and m.msg == "That computer isn't answering" and m.view != "text")
m.view = "list"

# the web page's eyes: other computers' files are fine, their hidden and private ones aren't
check("the web page may see them", m.web_may_see("net:") and m.web_may_see(S + "/net/127.0.0.1/Media/Films")
      and not m.web_may_see(S + "/net/127.0.0.1_2222/home/alice/.secret")
      and not m.web_may_see(S + "/net/127.0.0.1/Public/homeassistant.txt") and not m.web_may_see("/etc/passwd")
      and not m.web_may_see(S + "/net/not-a-computer/x"))

# forgetting one
m.browse("net:"); settle()
pick("127.0.0.1"); press("y")
check("Y once: asks", "Press Y again to forget 127.0.0.1" == m.msg and m.computers.get("127.0.0.1") is not None)
press("y"); settle()
check("Y again: forgotten, its folders closed", m.computers.get("127.0.0.1") is None
      and not [w for w in mounts() if "/net/127.0.0.1/" in w] and ("127.0.0.1", "netpc") not in rows())

# a restart: the computers kept, their folders opened again with the login kept
m.shutdown()
check("Pitato stopping closes them all", mounts() == [])
m2 = g.Media()
m2.enter(); m2.tab = bi; m2.view = "list"; m2.browse("net:")
m, m2 = m2, m
settle()
check("after a restart the computers are still there", ("127.0.0.1:2222", "netpc") in rows())
pick("127.0.0.1:2222"); press("a"); settle()
check("...and open without asking again", m.cwd == home and m.kb is None and m.computers.get("127.0.0.1:2222"))

# ======== the web page's Computers tab ==========================================================
sys.path.append(ROOT + "/pitato")   # (webui.py and camera.py are in the pitato folder now)
import webui
H = S + "/home/u"
os.environ["HOME"] = H
webui.HOME = H
webui.STATIC = ST = S + "/pitato/static"
os.makedirs(ST + "/fonts", exist_ok=True)
open(S + "/pitato/setup.sh", "w").write("echo hi\n")
webui.THUMBS = H + "/.cache/pitato/thumbs"
webui.STATE_FILE = g.STATE_FILE
webui.NET_ROOT = g.NET_ROOT
socket.gethostname = lambda: "gpi"
control = g.Control()
key = "k" * 32
server = g.serve_control(m, control, port=0, key=key)
open(S + "/control-key", "w").write(key)
webui.CONTROL = ("127.0.0.1", server.server_address[1])
webui.CONTROL_KEY = S + "/control-key"


class UI:
    def write(self, *a):
        pass

    def syn(self):
        pass


done = threading.Event()
loop = threading.Thread(target=lambda: g.run(UI(), m, control, stop=done.is_set), daemon=True)
loop.start()
time.sleep(0.4)
c = webui.app.test_client()
B = {"base_url": "http://gpi.local:5432", "headers": {"X-Pitato-Page": "1"}}


def post(path, body):
    return c.post(path, json=body, **B)


info = c.get("/api/info", **B).json
tab = next(f for f in info["folders"] if f["key"] == "computers")
check(f"Files has a Computers tab ({tab})", tab == {"key": "computers", "label": "Computers", "path": "Other computers",
                                                    "files": None})
r = c.get("/api/list?folder=computers&path=", **B).json
check(f"it lists the computers ({r['entries']})", [e["label"] for e in r["entries"]] == ["127.0.0.1:2222"]
      and r["entries"][0]["start"] == "127.0.0.1_2222/home/alice" and r["entries"][0]["computer"])
r = post("/api/pi/computer", {"do": "add", "address": "smb://127.0.0.1:4445"})
check(f"add one that wants a login: said so ({r.status_code} {r.json})", r.json.get("kind") == "login")
r = post("/api/pi/computer", {"do": "add", "address": "smb://127.0.0.1:4445", "user": "alice", "password": PW})
check(f"...with it: added ({r.json})", r.json.get("ok") and r.json["start"] == "127.0.0.1_4445"
      and r.json["shares"] == ["Media", "Public"])
r = c.get("/api/list?folder=computers&path=127.0.0.1_4445", **B).json
check(f"its shared folders ({r.get('entries')})", [e["name"] for e in r["entries"]] == ["Media", "Public"]
      and all(e["share"] and e["locked"] for e in r["entries"]))
r = c.get("/api/list?folder=computers&path=127.0.0.1_4445/Media", **B)
check(f"into one: opened by the Pi, read here ({r.json.get('entries')})", r.status_code == 200
      and [e["name"] for e in r.json["entries"]] == ["Films"] and r.json["entries"][0]["items"] is None
      and r.json["entries"][0]["locked"])
r = c.get("/api/list?folder=computers&path=127.0.0.1_2222/home/alice", **B).json
names = [e["name"] for e in r["entries"]]
check(f"an SSH one: the user's folder, no hidden files ({names})", "notes.txt" in names and ".secret" not in names
      and all(e["locked"] for e in r["entries"]))
r = c.get("/api/file?folder=computers&path=127.0.0.1_2222/home/alice/notes.txt", **B)
check("a file downloads", r.status_code == 200 and r.data == b"hello from alice\n")
r = c.get("/api/thumb?folder=computers&path=" + urllib.parse.quote("127.0.0.1_2222/home/alice/My Photos/red.jpg"), **B)
check(f"a picture's thumbnail ({r.status_code})", r.status_code == 200 and r.data[:2] == b"\xff\xd8")
for what, resp in (("upload", c.put("/api/upload?folder=computers&path=127.0.0.1_2222/home/alice/x.txt", data=b"x", **B)),
                   ("delete", post("/api/delete", {"folder": "computers", "path": "127.0.0.1_2222/home/alice/notes.txt"})),
                   ("exists", c.get("/api/exists?folder=computers&path=127.0.0.1_2222/home/alice/notes.txt", **B))):
    check(f"no {what} there ({resp.status_code})", resp.status_code == 403)
check("...the file's still there", os.path.exists(home + "/notes.txt"))
shutil.copy(g.COMPUTERS_FILE, S + "/net/../saved-copy.json")
for bad in ("../computers.json", "../saved-copy.json", "127.0.0.1_2222/../../computers.json", "%2e%2e/computers.json",
            "127.0.0.1_2222/../../../saved-copy.json"):
    r = c.get("/api/file?folder=computers&path=" + bad, **B)
    check(f"no way out of it to the Pi's own files ({bad}: {r.status_code})", r.status_code in (403, 404, 502)
          and PW.encode() not in r.data)
r = post("/api/pi/computer", {"do": "open", "path": "../etc"})
check("the Pi won't open a way out either", r.json.get("error"))
flag = S + "/proxied"
for user in ("-oProxyCommand=touch " + flag, "-F" + flag, "x,ProxyCommand=touch " + flag):
    r = post("/api/pi/computer", {"do": "add", "address": "ssh://127.0.0.1:2222", "user": user, "password": "x"})
    check(f"a user name that's an SSH option is turned away ({r.json.get('kind')})", r.json.get("kind") == "typo"
          and not os.path.exists(flag))
r = post("/api/pi/computer", {"do": "add", "address": "-oProxyCommand=touch " + flag + "@127.0.0.1"})
check("...in the address too", r.json.get("kind") == "typo" and not os.path.exists(flag))
check("a computer can't name a share '..'", g.share_dir("..") == "_.." and g.share_dir("a/b") == "a_b"
      and m.computers.folder({"addr": "pc"}, "..") == S + "/net/pc/_..")
r = post("/api/pi/show", {"folder": "computers", "path": "127.0.0.1_2222/home/alice/notes.txt"})
time.sleep(0.5)
check(f"shown on the Pi's screen ({r.json})", r.json.get("ok") and m.view == "text" and m.cwd == home)
m.view = "list"
subprocess.run(["umount", "-l", S + "/net/127.0.0.1_4445/Media"])
r = c.get("/api/list?folder=computers&path=127.0.0.1_4445/Media/Films", **B)
check("closed (a restart): opened again by itself", r.status_code == 200
      and [e["name"] for e in r.json["entries"]] == ["movie.mkv"])
r = post("/api/pi/computer", {"do": "forget", "addr": "127.0.0.1:4445"})
time.sleep(0.4)
r2 = c.get("/api/list?folder=computers&path=", **B).json
check("forgotten from the web page", r.json.get("ok") and [e["label"] for e in r2["entries"]] == ["127.0.0.1:2222"]
      and not [w for w in mounts() if "4445" in w])
check("a request from another site is turned away", c.post("/api/pi/computer", json={"do": "forget", "addr": "127.0.0.1:2222"},
                                                           base_url="http://gpi.local:5432",
                                                           headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403)
check("...and the list only goes to the page", c.get("/api/pi/computers", base_url="http://gpi.local:5432").status_code == 403)
done.set(); loop.join(5)
server.shutdown()
m.shutdown()
check("all closed at the end", mounts() == [])
shot.save(SP + "/out/net_files.png")
loading_shot.save(SP + "/out/net_loading.png")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
