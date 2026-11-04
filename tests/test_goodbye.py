"""Shutting down: the screen says so and stays; any other stop goes back to the terminal."""
import sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
g.STATE_FILE = SP + "/t51_state.json"
shots, calls = [], []
class FB:
    w, h = 640, 480
    def show(self, img): shots.append(img.copy())
    def close(self): calls.append("fb closed")
real_run = g.subprocess.run
def fake_run(cmd, *a, **k):
    calls.append(cmd[0])
    class R: stdout = "stopping\n" if STOPPING else "running\n"
    if cmd[0] in ("systemctl", "chvt"):
        return R()
    return real_run(cmd, *a, **k)
g.subprocess.run = fake_run
ok = []
for STOPPING in (True, False):
    calls.clear(); shots.clear()
    m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
    m.shutdown()
    if STOPPING:
        ok.append(bool(shots) and "chvt" not in calls and m.active)
        shots[-1].save(SP + "/goodbye.png")
        print("going down: 'Shutting down' stays on the screen:", ok[-1])
    else:
        ok.append("chvt" in calls and not m.active)
        print("a restart of the service: back to the terminal:", ok[-1])
print("ALL OK" if all(ok) else "FAILED")
