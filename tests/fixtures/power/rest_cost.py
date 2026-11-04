"""What resting saves: ticks, redraws and CPU, awake and resting, idle on the home screen and with music playing."""
import os, sys, time
SP = os.environ["PIETATO_TEST_WORK"]
exec(open(SP + "/power/idle_cost.py").read().split("def measure")[0])
import pitato.screens.rest as R
R.wifi_dev = lambda: ""
FB.power = lambda self, on: True


def measure(label, secs=20):
    draws[0] = 0
    ticks = 0
    t0, c0 = time.monotonic(), time.process_time()
    while time.monotonic() < t0 + secs:
        time.sleep(max(0.0, m.tick_limit()))
        m.tick(); m.flush(); ticks += 1
    wall, cpu = time.monotonic() - t0, time.process_time() - c0
    print(f"{label:34s} ticks/s {ticks / wall:4.1f}  redraws/s {draws[0] / wall:5.2f}  CPU {100 * cpu / wall:5.2f}%",
          flush=True)


class Proc:
    stdin = open(os.devnull, "w")
    def poll(self): return None


m.case = "2w"
for _ in range(10):
    m.tick(); m.flush()
time.sleep(2)
m.stir(); measure("home screen, awake", 15)
m.rest_start(); measure("home screen, resting", 15)
m.rest_end()
m.proc, m.kind = Proc(), "audio"
m.cur = g.item("/x/song.mp3", "song", "audio", "/x/song.mp3")
m.queue, m.qi, m.view, m.length_known = [m.cur], 0, "now", {}
m.dirty = True
m.stir(); measure("music playing, awake (now playing)", 15)
m.rest_start(); measure("music playing, resting", 15)
