"""state.json saved from several threads at once (the shrinker's, radio's, the main loop's): never a broken file."""
import json, os, sys, threading, shutil
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
S = SP + "/tsaverace"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S
ms = [g.Media(), g.Media()]
for k, m in enumerate(ms):
    m.state["pos"]["x" * (50 + 40 * k)] = k            # (different lengths: a mix would show)
bad, done = [], threading.Event()


def saver(m, n):
    for i in range(n):
        m.state["pos"]["i"] = i
        m.save_state()


def reader():
    while not done.is_set():
        try:
            json.load(open(g.STATE_FILE))
        except FileNotFoundError:
            pass
        except ValueError as ex:
            bad.append(str(ex))


ts = [threading.Thread(target=saver, args=(m, 400)) for m in ms for _ in range(2)]
r = threading.Thread(target=reader)
r.start()
for t in ts: t.start()
for t in ts: t.join()
done.set(); r.join()
left = [f for f in os.listdir(S) if f.endswith(".tmp")]
print(("ok   " if not bad and not left else "FAIL ") + f"saved from four threads at once: never a broken file ({len(bad)} bad reads {bad[:1]}, {left} left over)")
print("ALL OK" if not bad and not left else "FAILED")
