"""What media mode costs while nobody's touching it: ticks, redraws and CPU time, page by page (a pretend screen; the
main loop as app.py runs it, 4 times a second at most)."""
import os, sys, time, json, shutil, threading, resource
SP = os.environ["PIETATO_TEST_WORK"]
S = SP + "/power/t_idle"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games"):
    os.makedirs(f"{HOME}/{d}")
sys.path.insert(0, os.path.join(os.environ["PITATO_ROOT"], "tests")); sys.path.insert(0, SP)
import pietato_all as g
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, HOME)
real_run = g.subprocess.run
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
draws = [0]


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480
    def show(self, img): draws[0] += 1
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media()
m.enter()
threads0 = {t.name for t in threading.enumerate()}


def measure(label, secs=20):
    draws[0] = 0
    ticks = 0
    t0, c0 = time.monotonic(), time.process_time()
    end = t0 + secs
    while time.monotonic() < end:
        time.sleep(max(0.0, m.tick_limit()))
        m.tick(); m.flush(); ticks += 1
    wall, cpu = time.monotonic() - t0, time.process_time() - c0
    print(f"{label:28s} ticks/s {ticks / wall:5.1f}  redraws/s {draws[0] / wall:5.2f}  CPU {100 * cpu / wall:5.2f}%", flush=True)


measure("home screen")
for name in ("weather", "friend", "settings", "system", "music"):
    try:
        m.go_home(); m.tab = m.tab_index(name); m.view = "list"; m.load_tab(m.tab); m.dirty = True
        measure(f"tab: {name}")
    except Exception as ex:
        print(name, "skipped:", ex)
print("threads:", sorted(t.name for t in threading.enumerate()))
