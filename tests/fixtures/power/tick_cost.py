"""CPU time of one idle tick (nothing to redraw) and of one redraw, on the home screen and a few pages."""
import os, sys, time, shutil
SP = os.environ["PIETATO_TEST_WORK"]
sys.argv = [sys.argv[0]]
exec(open(SP + "/power/idle_cost.py").read().split("def measure")[0])   # (the same pretend Pi)
for _ in range(20):
    m.tick(); m.flush()
time.sleep(2)
for label, setup in (("home", lambda: (m.go_home(),)), ("bot (chat)", lambda: (m.go_home(), setattr(m, "tab", m.tab_index("friend")), setattr(m, "view", "list"), m.load_tab(m.tab)))):
    setup(); m.dirty = True; m.tick(); m.flush()
    n = 2000
    c0 = time.process_time()
    for _ in range(n):
        m.tick()
        m.flush()
    per_tick = (time.process_time() - c0) / n
    c0 = time.process_time()
    for _ in range(50):
        m.dirty = True
        m.flush()
    per_draw = (time.process_time() - c0) / 50
    print(f"{label:12s} idle tick {per_tick * 1e3:6.3f} ms CPU   redraw {per_draw * 1e3:6.1f} ms CPU   (draws during ticks: {draws[0]})")
