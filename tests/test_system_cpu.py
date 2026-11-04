"""System: how busy the CPU really is (from /proc/stat between looks, not the load average, which counted what's
waiting as well), with what Pietato's busy with in the background said under it (a video made smaller, lengths
read, thumbnails made); WiFi, the address and power looked at every 10 seconds rather than every 2; the first
look half a second after System opens."""
import os, shutil, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_syscpu"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.system as sysmod

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


# ---- how busy, worked out ------------------------------------------------------------------------------------------
STAT = S + "/stat"
sysmod.PROC_STAT = STAT


def stat(user, nice, system, idle, iowait, irq=0, softirq=0, steal=0):
    open(STAT, "w").write(f"cpu  {user} {nice} {system} {idle} {iowait} {irq} {softirq} {steal} 0 0\n"
                          "cpu0 1 2 3 4 5 6 7 8 0 0\n")


stat(100, 0, 50, 850, 0)
check(sysmod.cpu_busy() is None, "the first look: nothing to go by")
stat(150, 300, 70, 880, 100)                  # 500 ticks: 370 working (300 at a low priority), 130 idle or waiting
b = sysmod.cpu_busy()
check(b is not None and abs(b - 74.0) < 0.01, f"then: 74% ({b})")
stat(150, 300, 70, 1380, 100)
check(sysmod.cpu_busy() == 0.0, "nothing but idle: 0%")
stat(150, 300, 70, 1380, 600)
check(sysmod.cpu_busy() == 0.0, "waiting for the SD card isn't working: 0%")
sysmod._cpu_was = (0, 0, time.monotonic() - 60)
stat(150, 300, 70, 1400, 600)
check(sysmod.cpu_busy() is None, "a look long ago: nothing to go by")
sysmod.PROC_STAT = "/proc/stat"
sysmod.cpu_busy()
end = time.time() + 0.6
while time.time() < end:                       # (busy, on one of this machine's cores)
    pass
real = sysmod.cpu_busy()
cores = os.cpu_count()
check(real is not None and 100 / cores * 0.7 < real <= 100, f"the real one: {real:.0f}% with one of {cores} cores busy")

# ---- what takes a program, every 10 seconds -----------------------------------------------------------------------
ran = []
real_run = subprocess.run


def run(args, *a, **k):
    ran.append(args[0])
    return real_run(["true"], *a, **k)


sysmod.subprocess.run = run
sysmod._slow.clear()
rows1 = sysmod.system_info()
n1 = sorted(ran)
ran.clear()
rows2 = sysmod.system_info()
check(sorted(n1) == ["hostname", "iw", "vcgencmd"] and ran == [], f"a program for WiFi, the address and power: once ({n1}, then {ran})")
for k in sysmod._slow:
    sysmod._slow[k] = (time.monotonic() - 11, sysmod._slow[k][1])
sysmod.system_info()
check(sorted(ran) == ["hostname", "iw", "vcgencmd"], "...and again after 10 seconds")
sysmod.subprocess.run = real_run
labels = [r["title"] for r in rows2]
check(labels[:3] == ["CPU temperature", "CPU", "Power"], f"the rows: {labels[:4]}...")

# ---- media mode: System, with what's going on in the background ------------------------------------------------------
m = g.Media()
m.active = True
si = m.tab_index("system")


class FakeUpdater:
    new = 0

    def shown(self):
        return False

    def available(self):
        return False

    def poke(self):
        pass


m.updater = FakeUpdater()
sysmod._cpu_was = None                          # (System not looked at for a while)
m.tab, m.view = si, "list"
m.load_tab(si)
cpu = next(r for r in m.tab_items(si) if r["title"] == "CPU")
check(cpu["sub"].startswith("…"), f"System just opened: {cpu['sub']!r}")
BG = ("Converting video", "Converting videos", "Reading lengths", "Making thumbnails")
check(not any(r["title"] in BG for r in m.tab_items(si)), "nothing in the background: no such row")
time.sleep(0.9)
cpu = next(r for r in m.tab_items(si) if r["title"] == "CPU")
check("% busy" in cpu["sub"], f"half a second later: {cpu['sub']!r}")
sh = m.shrinker
sh.current, sh.pct, sh.queue = HOME + "/Videos/Big Film (2019).mkv", 35, [HOME + "/Videos/Big Film (2019).mkv",
                                                                      HOME + "/Videos/Other.mp4"]
m.probe_left, m.thumbs_left = 120, 0
time.sleep(2.2)
bg = [(r["title"], r["sub"]) for r in m.tab_items(si) if r["title"] in BG]
check(bg == [("Converting videos", "35% · Big Film (2019) · 1 more after it"),
             ("Reading lengths", "120 songs and videos left")], f"in the background: {bg}")
titles = [r["title"] for r in m.tab_items(si)]
check(titles.index("Converting videos") == titles.index("CPU") + 1, "...said just after how busy the CPU is")


class FB:
    w, h = 640, 480

    def show(self, img):
        self.img = img.copy()

    def close(self):
        pass


m.load_fonts()
m.fb = FB()
m.set_setting("sys_view", "List")              # (the list's picture: System opens on its dashboard)
m.sels[si] = 0
m.dirty = True
m.flush()
m.fb.img.save(S + "/system.png")
sh.queue = [sh.current]
m.probe_left, m.thumbs_left = 0, 40
m.items[si] = m.system_rows()
bg = [(r["title"], r["sub"]) for r in m.tab_items(si) if r["title"] in BG]
check(bg == [("Converting video", "35% · Big Film (2019)"), ("Making thumbnails", "40 photos left")], f"...{bg}")
# rows coming and going above the one you're on: still on it (A never lands on another button)
keys = [r["key"] for r in m.tab_items(si)]
m.sels[si] = keys.index("act:reboot")
sh.current = None
m.thumbs_left = 0
m.system_show(m.system_rows())
now = m.tab_items(si)
check(len(now) == len(keys) - 2 and now[m.sels[si]]["key"] == "act:reboot",
      f"two rows gone above Reboot: still on Reboot ({now[m.sels[si]]['title']})")
m.probe_left = 7
m.system_show(m.system_rows())
now = m.tab_items(si)
check(now[m.sels[si]]["key"] == "act:reboot" and any(r["title"] == "Reading lengths" for r in now),
      f"...one come: still on Reboot ({now[m.sels[si]]['title']})")
m.sels[si] = next(k for k, r in enumerate(now) if r["title"] == "Reading lengths")
m.probe_left = 0
m.system_show(m.system_rows())
now = m.tab_items(si)
check(0 <= m.sels[si] < len(now), f"...the row you were on gone: a row still picked ({now[m.sels[si]]['title']})")
m.active = False
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
