"""webui.py's Sound here, by itself: while a page plays what it's sent (it says so every couple of seconds), media mode
is told Sound here is on; a page that stops saying so (a phone that locked) and the Pi is told it's off, and on again
when it does; the last page gone, off."""
import os, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
os.environ["HOME"] = SP + "/t_soundout_home"
os.environ["PATH"] = SP + "/soundstub/bin:" + os.environ["PATH"]
sys.path.insert(0, ROOT + "/pitato")
import webui
told = []
webui.tell_pi = lambda what, on: told.append((round(time.monotonic(), 2), what, on)) or {}
webui.SOUND_HEARD = 1.5
ok_all = []
def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)
S = webui.SoundOut()
q = S.join()
got = []
def page():                                    # (a page reading what it's sent)
    while True:
        c = q.get(timeout=5)
        if c is None:
            break
        got.append(len(c))
threading.Thread(target=page, daemon=True).start()
for _ in range(10):
    S.playing(); time.sleep(0.3)
check(f"a page playing it: on ({[t[2] for t in told]}, {sum(got)} bytes)", told and all(t[2] for t in told) and sum(got) > 100000)
n = len(told)
time.sleep(2.5)                                # (it stops saying so)
check(f"...it stops saying it's playing it: off ({[t[2] for t in told[n:]]})", told[n:] and told[-1][2] is False)
S.playing(); time.sleep(0.6)
check(f"...says so again: on ({told[-1][2]})", told[-1][2] is True)
S.leave(q); time.sleep(0.8)
check(f"the page gone: off, and nothing more ({told[-1]})", told[-1][2] is False and S.proc is None)
n = len(told); time.sleep(1)
check("...nothing more said", len(told) == n)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
