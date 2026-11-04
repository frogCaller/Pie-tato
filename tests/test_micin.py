"""webui.py's Mic here, by itself: what a page's microphone sends goes to aplay (into the Loopback card), and media mode
is told it's on every few seconds while it comes, with its answer (listening, or why not) given back to the page each
time it sends; it stops coming: aplay stopped, and media mode told it's off."""
import os, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
os.environ["HOME"] = SP + "/t_micin_home"
os.environ["PATH"] = SP + "/soundstub/bin:" + os.environ["PATH"]
sys.path.insert(0, ROOT + "/pitato")
import webui
told, answers = [], [{"ok": True, "listens": False, "why": "Set up your bot first: Settings › Bot"}]
slow = [0.0]                                     # (how long media mode takes to answer)


def tell_pi(what, on):
    told.append((what, on))
    time.sleep(slow[0])
    return answers[-1] if on else {}


webui.tell_pi = tell_pi
webui.SAY_EVERY, webui.MIC_QUIET = 0.5, 1.0
webui.LOOPBACK = SP + "/t_micin_home"            # (the Loopback card setup.sh adds: here)
os.makedirs(webui.LOOPBACK, exist_ok=True)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


app = webui.app.test_client()
webui.app.config["TESTING"] = True
outs = []
for k in range(8):                               # (two seconds of a page's microphone, a quarter at a time)
    if k == 4:
        answers.append({"ok": True, "listens": True})
    r = app.post("/api/mic", data=b"\0\1" * 2000, headers={"Content-Type": "application/octet-stream"},
                 environ_base={"REMOTE_ADDR": "127.0.0.1"})
    outs.append((r.status_code, r.get_json()))
    time.sleep(0.25)
mic_says = [t for t in told if t == ("webmic", True)]
check(f"media mode told it's on, again and again while it comes ({len(mic_says)} times)", len(mic_says) >= 3)
check(f"...why it isn't listening, given to the page ({outs[2]})",
      outs[2] == (200, {"ok": True, "listens": False, "why": "Set up your bot first: Settings › Bot"}))
check(f"...and once it is, just that ({outs[-1]})", outs[-1] == (200, {"ok": True, "listens": True}))
time.sleep(1.8)
check(f"it stops coming: aplay stopped, media mode told it's off ({told[-1]}, {webui.MIC.proc})",
      told[-1] == ("webmic", False) and webui.MIC.proc is None)

# another time: what media mode said the last time isn't said again
answers.append({"ok": True, "listens": False, "why": "The Pi is getting what it listens with (45 MB): a minute or two"})
for k in range(4):
    r = app.post("/api/mic", data=b"\0\1" * 2000, headers={"Content-Type": "application/octet-stream"},
                 environ_base={"REMOTE_ADDR": "127.0.0.1"})
    time.sleep(0.25)
check(f"...the next time, why not ({r.get_json()})", r.get_json().get("why", "").startswith("The Pi is getting"))
time.sleep(1.8)
answers.append({"ok": True, "listens": False, "why": "Set up your bot first: Settings › Bot"})
slow[0] = 0.5
r = app.post("/api/mic", data=b"\0\1" * 2000, headers={"Content-Type": "application/octet-stream"},
             environ_base={"REMOTE_ADDR": "127.0.0.1"})
check(f"...and the time after: not that again, before media mode's answered ({r.get_json()})",
      r.get_json() == {"ok": True, "listens": True})
time.sleep(0.8)
r = app.post("/api/mic", data=b"\0\1" * 2000, headers={"Content-Type": "application/octet-stream"},
             environ_base={"REMOTE_ADDR": "127.0.0.1"})
check(f"...then what it says now ({r.get_json()})", r.get_json().get("why") == "Set up your bot first: Settings › Bot")
time.sleep(2.5)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
