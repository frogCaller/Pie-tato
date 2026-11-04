"""For the Bluetooth tests: the pretend BlueZ's state file and the stand-ins first on PATH."""
import fcntl
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import btstate  # noqa: E402  (its links folder, kept as the state changes)


def use(folder, state):
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    env = {"BT_FAKE": folder + "/bt.json", "BT_LOG": folder + "/bt.log",
           "BT_AGENT_IN": folder + "/agent_in", "BT_AGENT_OUT": folder + "/agent_out",
           "BT_LINKS": folder + "/links"}
    os.environ.update(env)
    os.environ["PATH"] = HERE + "/bin:" + os.environ["PATH"].replace(HERE + "/bin:", "")
    put(state)
    open(env["BT_AGENT_IN"], "w").close()
    return env


def put(state):
    """(Locked, as the stand-ins lock it: one of them reading it half-written would trip over it.)"""
    path = os.environ["BT_FAKE"]
    if not os.path.exists(path):
        open(path, "w").close()
    with open(path, "r+") as f:
        fcntl.lockf(f, fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        json.dump(state, f)
        f.flush()
        btstate.sync_links(state)
        fcntl.lockf(f, fcntl.LOCK_UN)


def get():
    with open(os.environ["BT_FAKE"]) as f:
        fcntl.lockf(f, fcntl.LOCK_SH)
        s = json.load(f)
        fcntl.lockf(f, fcntl.LOCK_UN)
    return s


def change(fn):
    """fn(state) changes it, all under the lock."""
    with open(os.environ["BT_FAKE"], "r+") as f:
        fcntl.lockf(f, fcntl.LOCK_EX)
        s = json.load(f)
        fn(s)
        f.seek(0)
        f.truncate()
        json.dump(s, f)
        f.flush()
        btstate.sync_links(s)
        fcntl.lockf(f, fcntl.LOCK_UN)


def log():
    try:
        return open(os.environ["BT_LOG"]).read().splitlines()
    except OSError:
        return []


STATE = {"running": True, "adapter": True, "powered": True, "blocked": False, "discovering": False,
         "devices": {
             "E4:17:D8:00:00:01": {"name": "8BitDo SN30 Pro", "icon": "input-gaming", "paired": True,
                                   "trusted": True, "connected": True},
             "DC:2C:26:00:00:02": {"name": "Keyboard K380", "icon": "input-keyboard", "paired": True,
                                   "trusted": True, "connected": False},
             "AA:BB:CC:00:00:09": {"name": None, "rssi": -40},          # (a beacon: no name)
         },
         "nearby": {
             "98:B6:E9:00:00:03": {"name": "Pro Controller", "icon": "input-gaming", "rssi": -48},
             "00:1B:66:00:00:04": {"name": "WH-1000XM4", "icon": "audio-headphones", "rssi": -61,
                                   "connect": "profile"},
             "54:46:6B:00:00:05": {"name": "Logi K480", "rssi": -70, "pair": "code", "code": "482915"},
             "F0:99:B6:00:00:06": {"name": "Pixel 8", "icon": "phone", "rssi": -80, "pair": "confirm"},
             "11:22:33:00:00:07": {"name": "Old Pad", "icon": "input-gaming", "rssi": -85, "pair": "fail-auth"},
         }}
