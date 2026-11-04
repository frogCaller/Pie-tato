"""Bluetooth's look round against the real busctl: BlueZ's devices as a Pi sees them while it looks (phones and
earbuds sending their makers' data, which busctl --json can't give: it gives up and says nothing, and Pitato said
Bluetooth wasn't running), read from busctl's own printing. A stand-in BlueZ (btreal/fake_bluez.py) on a private
D-Bus answers; busctl is the real one."""
import os
import subprocess
import sys
import time

from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP + "/btfake")
sys.path.insert(0, ROOT)
import btstate as B  # noqa: E402
from pitato import bluetooth as bt  # noqa: E402

REAL = SP + "/btreal"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


V = lambda t, d: {"type": t, "data": d}  # noqa: E731

# ---- reading busctl's printing ----------------------------------------------------------------------
line = r'a{sv} 3 "Name" s "Sam\342\200\231s \"Buds\" \\ \t" "RSSI" n -61 "Maker" a{qv} 1 76 ay 3 1 2 255'
sig, vals = bt.bus_reply(line)
check("a dict of variants: text with C's escapes and octal UTF-8, a number, and a{qv} keyed by numbers",
      sig == "a{sv}" and vals == [{"Name": V("s", 'Sam’s "Buds" \\ \t'), "RSSI": V("n", -61),
                                   "Maker": V("a{qv}", {76: V("ay", [1, 2, 255])})}])
check("several types, empty ones, a struct, a double, true/false, an object path",
      bt.bus_reply('sa{sv}as(sb)do "hi" 0 0 "x" true 1.5 "/org/bluez/hci0"\n') ==
      ("sa{sv}as(sb)do", ["hi", {}, [], ["x", True], 1.5, "/org/bluez/hci0"]))
check("nested: an array of structs holding dicts", bt.bus_reply('a(sa{sv}) 2 "k" 1 "p" b false "j" 0') ==
      ("a(sa{sv})", [[["k", {"p": V("b", False)}], ["j", {}]]]))
check("bytes that aren't UTF-8: replaced, not a crash", bt.bus_reply(r's "\377ok"') == ("s", ["�ok"]))
for bad in ('a{sv} 2 "Name" s "x"', "", 'a{sv} x', 'n "notanumber"'):
    try:
        bt.bus_reply(bad)
        check(f"a reply cut short or wrong ({bad!r}): an error", False)
    except (ValueError, IndexError, KeyError, TypeError):
        check(f"a reply cut short or wrong ({bad!r}): an error", True)
weird = 'tab\there "q" \\ ’ \x01 é'
check("the stand-in's escaping, read back", bt.bus_reply("s " + '"' + B.cescape(weird) + '"') == ("s", [weird]))

# ---- the real busctl, and a BlueZ looking round -----------------------------------------------------
os.makedirs(REAL + "/bin", exist_ok=True)
wrap = REAL + "/bin/busctl"
with open(wrap, "w") as f:
    f.write('#!/bin/sh\nif [ -n "$BT_FAIL" ]; then echo "Call failed: Connection timed out" >&2; exit 1; fi\n'
            'exec /usr/bin/busctl --address="$BT_ADDR" "$@"\n')
os.chmod(wrap, 0o755)
out = subprocess.run(["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1"],
                     capture_output=True, text=True, timeout=20).stdout.split()
ADDR, DPID = out[0], int(out[1])
os.environ["BT_ADDR"] = ADDR
os.environ["PATH"] = REAL + "/bin:" + os.environ["PATH"].replace(SP + "/btfake/bin:", "")
procs = []


def start_bluez():
    log = open(REAL + "/fake.log", "w")
    p = subprocess.Popen(["python3.12", "-I", REAL + "/fake_bluez.py", ADDR], stdout=log, stderr=subprocess.STDOUT)
    procs.append(p)
    end = time.monotonic() + 15
    while time.monotonic() < end and "ready" not in open(REAL + "/fake.log").read():
        time.sleep(0.05)
    return p


try:
    fake = start_bluez()
    ask = ["/usr/bin/busctl", "--address=" + ADDR, "call", "org.bluez", "/", "org.freedesktop.DBus.ObjectManager",
           "GetManagedObjects"]
    js = subprocess.run(ask[:2] + ["--json=short"] + ask[2:], capture_output=True, text=True, timeout=20)
    check(f"why it went wrong: the real busctl --json gives up on the makers' data, saying nothing "
          f"(rc {js.returncode}, {len(js.stdout)} bytes out)", js.returncode != 0 and not js.stdout.strip())
    plain = subprocess.run(ask, capture_output=True, text=True, timeout=20)
    sig, vals = bt.bus_reply(plain.stdout)
    objs = vals[0]
    pix = objs.get("/org/bluez/hci0/dev_4C_87_5D_11_22_33", {}).get("org.bluez.Device1", {})
    pods = objs.get("/org/bluez/hci0/dev_70_F9_4A_44_55_66", {}).get("org.bluez.Device1", {})
    keys = objs.get("/org/bluez/hci0/dev_E4_17_D8_77_88_99", {}).get("org.bluez.Device1", {})
    check("...while without it, every device comes back: the adapter, the makers' data, the names as they are",
          plain.returncode == 0 and sig == "a{oa{sa{sv}}}" and len(objs) == 7
          and objs["/org/bluez/hci0"]["org.bluez.Adapter1"]["Powered"] == V("b", True)
          and pix.get("ManufacturerData") == V("a{qv}", {224: V("ay", [1, 2, 3, 4])})
          and pix.get("RSSI") == V("n", -58) and pods.get("Name") == V("s", "Sam’s AirPods")
          and pods.get("AdvertisingData") == V("a{yv}", {255: V("ay", [0x4c, 0x00, 0x07])})
          and keys.get("Name") == V("s", 'My "Keys" \\ Pad\tX'))
    check("the tests' stand-in busctl prints exactly what the real one does",
          "a{oa{sa{sv}}} " + B.busctl_text(sig, objs) == plain.stdout.rstrip("\n"))

    b = bt.Bluetooth()
    b.refresh()
    s = b.snapshot()
    got = [(d["name"], d["kind"], d["paired"], d["connected"]) for d in s["devices"]]
    check(f"Pitato's look: on, your keyboard, then the ones nearby nearest first, the nameless beacon left out ({got})",
          s["there"] is True and s["on"] and s["why"] == "" and got == [
              ("BBQ20KBD", "keyboard", True, True), ("Pixel 8", "phone", False, False),
              ("Sam’s AirPods", "headphones", False, False), ('My "Keys" \\ Pad X', "controller", False, False)])

    bt.BT_STALE = 0.6
    os.environ["BT_FAIL"] = "1"
    b.refresh()
    s = b.snapshot()
    check("a look that fails now and then: the list stays as it was", s["there"] is True and len(s["devices"]) == 4)
    time.sleep(0.8)
    b.refresh()
    s = b.snapshot()
    check(f"...not answering for a while: said so, and not that it isn't running ({s['why']!r})",
          s["there"] is False and s["why"] == "Bluetooth isn't answering" and b.look() == "Bluetooth isn't answering")
    del os.environ["BT_FAIL"]
    b.refresh()
    check("...answering again: back", b.snapshot()["there"] is True and len(b.snapshot()["devices"]) == 4)

    fake.terminate()
    fake.wait(10)
    b.refresh()
    s = b.snapshot()
    check(f"BlueZ gone: Bluetooth isn't running, said at once ({s['why']!r})",
          s["there"] is False and s["why"] == "Bluetooth isn't running on this Pi")
    start_bluez()
    b.refresh()
    check("...and back when it is", b.snapshot()["there"] is True and b.snapshot()["on"])
finally:
    for p in procs:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
    try:
        os.kill(DPID, 15)
    except (OSError, NameError):
        pass

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
