"""Bluetooth (pitato/bluetooth.py) against a pretend BlueZ: stand-in busctl, bluetoothctl and rfkill."""
import copy
import os
import sys
import time

from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP + "/btfake")
sys.path.insert(0, ROOT)
import setup_env as F
from pitato import bluetooth as bt

S = SP + "/tbt"
F.use(S, copy.deepcopy(F.STATE))
bt.BT_EVERY, bt.BT_WEB, bt.BT_LOOK, bt.BT_SUMMARY = 0.4, 2.0, 6.0, 1.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=8.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


# ---- words ------------------------------------------------------------------------------
check("kinds: BlueZ's icon first, then the name", bt.bt_kind("input-gaming", "") == "controller"
      and bt.bt_kind(None, "Xbox Wireless Controller") == "controller" and bt.bt_kind("", "Logi K480") == "keyboard"
      and bt.bt_kind(None, "Galaxy Buds2") == "headphones" and bt.bt_kind("audio-card", "x") == "speaker"
      and bt.bt_kind(None, "Some Thing") == "")
check("BlueZ's errors in words", bt.bt_why("Authentication Failed").startswith("It didn't pair")
      and bt.bt_why("Page Timeout", "pair").endswith("in pairing mode, and close by?")
      and bt.bt_why("Page Timeout", "connect").endswith("Is it on, and close by?")
      and bt.bt_why("br-connection-profile-unavailable") == "The Pi has nothing it can connect it to"
      and bt.bt_why("Unknown object '/org/bluez/hci0/dev_X'.") == "It's gone. Look again"
      and bt.bt_why("Blocked through rfkill") == "Bluetooth is switched off on this Pi"
      and bt.bt_why("Something odd") == "It didn't work (Something odd)")
check("colours and the prompt's markers stripped", bt.ANSI.sub("", "\x1b[K\x1b[0;93m[agent]\x1b[0m Passkey: "
                                                               "\x1b[1;39m123456\x1b[0m\x01\x02") ==
      "[agent] Passkey: 123456")

# ---- what's there -------------------------------------------------------------------------
b = bt.Bluetooth()
seen = []
b.on_change = lambda: seen.append(time.monotonic())
b.refresh()
s = b.snapshot()
names = [d["name"] for d in s["devices"]]
check(f"there, on; yours: connected first, the one with no name left out ({names})",
      s["there"] is True and s["on"] and names == ["8BitDo SN30 Pro", "Keyboard K380"]
      and s["devices"][0]["connected"] and s["devices"][0]["what"] == "Controller"
      and s["devices"][1]["kind"] == "keyboard" and not s["looking"])
check("no bluetoothctl yet (not looking)", not b.agent.alive())

# ---- looking round, while a page shows it --------------------------------------------------
b.watch("screen", True)
check("a page open: its thread runs", until(lambda: b.thread is not None and b.thread.is_alive(), 2))
check("...and bluetoothctl, as the agent", until(lambda: b.agent.alive() and b.agent.ready.is_set(), 4))
check("...made the default agent", until(lambda: any("got default-agent" in l for l in F.log()), 3))
check("not looking round yet", not any("got scan on" in l for l in F.log()))
check("look: started", b.look() is None and b.snapshot()["looking"])
check("...scan on", until(lambda: any("got scan on" in l for l in F.log()), 4))
check("...the ones nearby, nearest first, the controller in pairing mode at the top",
      until(lambda: [d["name"] for d in b.snapshot()["devices"] if not d["paired"]] ==
            ["Pro Controller", "WH-1000XM4", "Logi K480", "Pixel 8", "Old Pad"], 6))
near = {d["name"]: d for d in b.snapshot()["devices"]}
check("...each said what it is", near["Pro Controller"]["what"] == "Controller"
      and near["WH-1000XM4"]["what"] == "Headphones" and near["Logi K480"]["what"] == "Keyboard"
      and near["Pixel 8"]["what"] == "Phone")
check(f"...it said so as it went ({len(seen)} changes)", len(seen) >= 3)

# ---- pairing ----------------------------------------------------------------------------------
before = len(F.log())
check("pair a controller: started", b.pair("98:b6:e9:00:00:03") is None and b.snapshot()["busy"] == "pair")
check("...one thing at a time", b.connect("DC:2C:26:00:00:02") == "One thing at a time. Try again in a moment")
check("...its status", "Pro Controller" in (b.snapshot()["status"] or ""))
check("...done: connected", until(lambda: b.snapshot()["busy"] is None, 10)
      and b.snapshot()["status"] == "Pro Controller is connected")
st = F.get()["devices"]["98:B6:E9:00:00:03"]
check("...paired, trusted (it comes back by itself) and connected", st["paired"] and st["trusted"] and st["connected"])
lines = F.log()[before:]
off = next((i for i, l in enumerate(lines) if "got scan off" in l), None)
pair = next((i for i, l in enumerate(lines) if l.split()[1:2] == ["busctl"] and "Pair" in l), None)
check(f"...the looking stopped first ({off}, {pair})", off is not None and pair is not None and off < pair)
d = next(d for d in b.snapshot()["devices"] if d["name"] == "Pro Controller")
order = [x["name"] for x in b.snapshot()["devices"]]
check(f"...and now it's one of yours ({order[:3]})", d["paired"] and d["connected"]
      and order[:2] == ["8BitDo SN30 Pro", "Pro Controller"])

# a keyboard: its code to type
b.look()
codes = []
real = b.got_code
b.got_code = lambda code: (codes.append(code), real(code))
b.agent.on_code = b.got_code
check("a keyboard: pairing", b.pair("54:46:6B:00:00:05") is None)
check("...its code to type in, passed on", until(lambda: b.snapshot()["code"] == "482915", 5))
check("...then done, the code gone", until(lambda: b.snapshot()["busy"] is None, 10)
      and b.snapshot()["code"] is None and b.snapshot()["status"] == "Logi K480 is connected")
check(f"...the code read through its colours, as each digit was typed ({codes})", "482915" in codes
      and all(c in ("482915", None) for c in codes))

# a phone: yes, it's the same number
check("a phone: pairing", b.pair("F0:99:B6:00:00:06") is None)
check("...the question answered yes, once (asked twice over)", until(lambda: b.snapshot()["busy"] is None, 10)
      and F.get()["devices"]["F0:99:B6:00:00:06"]["paired"]
      and sum(1 for l in F.log() if l.endswith("got yes")) == 1)

# one that won't
check("one that won't pair", b.pair("11:22:33:00:00:07") is None)
check("...said why", until(lambda: b.snapshot()["busy"] is None, 10)
      and b.snapshot()["status"] == "Old Pad: It didn't pair. Put it in pairing mode, and try again")

# headphones: paired, but nothing to play through them (no BlueALSA)
check("headphones: pairing", b.pair("00:1B:66:00:00:04") is None)
check("...paired; said to run setup.sh again for their sound", until(lambda: b.snapshot()["busy"] is None, 10)
      and b.snapshot()["status"] == "WH-1000XM4 is paired. To hear sound through it, run setup.sh again")

# ---- yours: connect, disconnect, forget ---------------------------------------------------------
check("connect the keyboard", b.connect("DC:2C:26:00:00:02") is None
      and until(lambda: b.snapshot()["busy"] is None, 8) and b.snapshot()["status"] == "Keyboard K380 is connected")
check("disconnect it", b.disconnect("DC:2C:26:00:00:02") is None
      and until(lambda: b.snapshot()["busy"] is None, 8) and b.snapshot()["status"] == "Keyboard K380 is disconnected"
      and not F.get()["devices"]["DC:2C:26:00:00:02"]["connected"])
# its last word comes as it's done, never while it's still busy (the next thing asked then would be turned away)
check("connect it again", b.connect("DC:2C:26:00:00:02") is None)
looks, end = [], time.monotonic() + 8
while time.monotonic() < end:
    s = b.snapshot()
    looks.append((s["status"], s["busy"]))
    if s["busy"] is None:
        break
    time.sleep(0.002)
early = [x for x in looks if x[0] == "Keyboard K380 is connected" and x[1]]
check(f"...said it's connected only once it was done ({len(looks)} looks, {len(early)} too soon)",
      not early and looks[-1] == ("Keyboard K380 is connected", None))
started = b.forget("DC:2C:26:00:00:02")
done = until(lambda: b.snapshot()["busy"] is None, 8)
check(f"forget it ({started}, {b.snapshot()['status']!r}, {[d['name'] for d in b.snapshot()['devices']]})",
      started is None and done and b.snapshot()["status"] == "Forgot Keyboard K380"
      and "DC:2C:26:00:00:02" not in F.get()["devices"]
      and "Keyboard K380" not in [d["name"] for d in b.snapshot()["devices"]])
check("a device that isn't there", b.connect("00:00:00:00:00:00") == "It's gone. Look again")

# ---- the web page's requests ----------------------------------------------------------------
check("web: a bad address", b.do("pair", "nope") == {"error": "No such device"})
check("web: unknown", b.do("dance") == {"error": "Unknown request"})
mark = len(F.log())
check("web: look", b.do("look") == {"ok": True} and b.snapshot()["looking"])
check("...scan on", until(lambda: any("got scan on" in l for l in F.log()[mark:]), 4))
mark = len(F.log())
check("web: stop", b.do("stop") == {"ok": True} and not b.snapshot()["looking"])
check("...scan off", until(lambda: any("got scan off" in l for l in F.log()[mark:]), 3))

# ---- on and off ---------------------------------------------------------------------------------
check("off", b.do("off") == {"ok": True} and until(lambda: b.snapshot()["busy"] is None, 6)
      and b.snapshot()["on"] is False and not F.get()["powered"])
check("...looking can't, then", b.look() == "Bluetooth is off" and b.pair("E4:17:D8:00:00:01") == "Bluetooth is off")
F.change(lambda st: st.update(blocked=True))
check("on, through rfkill's block", b.do("on") == {"ok": True} and until(lambda: b.snapshot()["busy"] is None, 8)
      and b.snapshot()["on"] and F.get()["powered"] and not F.get()["blocked"]
      and any("rfkill unblock bluetooth" in l for l in F.log()))
check("...and looking again, with a page open", b.snapshot()["looking"])

# ---- no page: it lets go -------------------------------------------------------------------------
b.watch("screen", False)
check("page closed: done looking", not b.snapshot()["looking"])
check("...its thread ends, and bluetoothctl with it", until(lambda: b.thread is None and not b.agent.alive(), 6))
b.watch("web")
check("the web page asking: on again for a while", until(lambda: b.agent.alive(), 4))
check("...then, unasked, off", until(lambda: b.thread is None and not b.agent.alive(), 8))

# ---- Settings' first page: a look now and then ----------------------------------------------------
b2 = bt.Bluetooth()
s = b2.summary()
check("summary: not looked yet, then looked on a thread", s["there"] is None
      and until(lambda: b2.snapshot()["there"] is True, 4))

# ---- no Bluetooth --------------------------------------------------------------------------------
F.change(lambda st: st.update(running=False))
b3 = bt.Bluetooth()
b3.refresh()
check("BlueZ not running: said so", b3.snapshot()["there"] is False
      and b3.snapshot()["why"] == "Bluetooth isn't running on this Pi" and b3.look() == "Bluetooth isn't running on this Pi")
F.change(lambda st: st.update(running=True, adapter=False))
b3.refresh()
check("no adapter: said so", b3.snapshot()["why"] == "This Pi has no Bluetooth" and b3.pair("E4:17:D8:00:00:01") ==
      "It's gone. Look again")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
