"""Settings > Bluetooth on the Pi's screen, against the pretend BlueZ (btfake): its row on Settings' first page, the
page (yours, nearby, headings skipped), pairing a controller and a keyboard (its code, big), connecting,
disconnecting and forgetting (asked twice), on and off (off asked twice), X, B, and letting go when it's left."""
import copy, json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP + "/btfake")
sys.path.insert(0, TESTS)
import setup_env as F
import pietato_all as g
from PIL import ImageDraw
S = SP + "/t_bt_page"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
F.use(S + "/bt", copy.deepcopy(F.STATE))
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: S + "/home/u"
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
g.BT_EVERY, g.BT_LOOK, g.BT_SUMMARY = 0.4, 20.0, 0.5
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=8.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        m.tick()
        if m.dirty:
            m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return cond()


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]


def drawn():
    texts.clear(); m.dirty = True; m.flush()
    return list(texts)


def shot(name):
    FB.last.save(f"{S}/{name}.png")


m = g.Media(); m.enter()
si = m.tab_index("settings")
m.open_app(si)
m.set_page, m.set_sel = "root", 0
rows = [k for k, _, _ in m.settings_rows()]
check(f"Settings: Bluetooth after WiFi ({rows[:3]})", rows[:2] == ["wifi", "bluetooth"])
m.set_sel = 1
drawn()
check("...its row says what's connected, once it's looked", until(lambda: "1 connected" in drawn(), 4))
t = drawn()
check("...A: Devices", "Devices" in t)
shot("root")

# ---- the page ---------------------------------------------------------------------------
m.press("a")
check("A: the page, and looking round", m.set_page == "bluetooth" and until(lambda: m.bt.snapshot()["looking"], 2))
check("...the ones nearby come up, under a heading", until(lambda: "Nearby" in drawn() and "Pro Controller" in texts, 8))
rows = m.settings_rows()
keys = [k for k, _, _ in rows]
check(f"rows: the switch; yours under a heading; nearby under a heading ({keys})",
      keys == ["bt_power", "bt_head", "bt_dev", "bt_dev", "bt_head", "bt_new", "bt_new", "bt_new", "bt_new", "bt_new"]
      and rows[1][1] == "Your devices" and rows[4][1] == "Nearby")
t = drawn()
check("drawn: crumb, Looking…, your devices' state, what each nearby one is",
      "Settings  ›  Bluetooth" in t and "Looking…" in t and "Connected" in t and "Not connected" in t
      and "Controller" in t and "Headphones" in t and "Looking for devices. Put yours in pairing mode" in t)
check("...the switch picked first: ◀▶ On / off, X Look again, B Back", m.bt_sel(rows) == 0
      and "On / off" in t and "Look again" in t and "Back" in t)
shot("page")
m.press("down")
check("down: past the heading, to the first of yours", m.bt_pick == "E4:17:D8:00:00:01")
t = drawn()
check("...A Disconnect (it's connected), Y Forget", "Disconnect" in t and "Forget" in t)
m.press("down"); m.press("down")
check("down twice: past the next heading, to the nearest one nearby", m.bt_pick == "98:B6:E9:00:00:03")
check("...A Pair", "Pair" in drawn())
m.press("up")
check("up: back past the heading", m.bt_pick == "DC:2C:26:00:00:02")
m.press("down")

# ---- pairing a controller ------------------------------------------------------------------
m.press("a")
check("A: pairing it", m.bt.snapshot()["busy"] == "pair" and "Pairing…" in drawn())
check("...connected, and now one of yours, still picked",
      until(lambda: m.bt.snapshot()["busy"] is None, 10) and m.bt_pick == "98:B6:E9:00:00:03"
      and [k for k, _, _ in m.settings_rows()][m.bt_sel(m.settings_rows())] == "bt_dev")
t = drawn()
check("...said so", "Pro Controller is connected" in t)
shot("paired")

# ---- a keyboard: its code, big --------------------------------------------------------------
m.press("x")
check("X: looking again", until(lambda: m.bt.snapshot()["looking"], 3))
rows = m.settings_rows()
k = next(k for k, r in enumerate(rows) if r[0] == "bt_new" and r[2]["name"] == "Logi K480")
m.bt_choose(rows, k)
dev = F.get()["nearby"]
F.change(lambda st: st["devices"]["54:46:6B:00:00:05"].update(typing=3.0))
m.press("a")
check("A on a keyboard: its code to type, big", until(lambda: "Type this on the keyboard" in drawn(), 6)
      and "then press Enter on it" in texts
      and all(c in texts for c in "482915"))
shot("code")
check("...then gone, and it's connected", until(lambda: m.bt.snapshot()["busy"] is None, 12)
      and "Type this on the keyboard" not in drawn() and "Logi K480 is connected" in texts)

# ---- yours: disconnect (asked twice), connect, forget (asked twice) ---------------------------------
rows = m.settings_rows()
m.bt_choose(rows, next(k for k, r in enumerate(rows) if r[0] == "bt_dev" and r[2]["name"] == "Logi K480"))
m.press("a")
check("A on a connected one: asked first", m.msg == "Press A again to disconnect it" and m.bt.snapshot()["busy"] is None)
m.press("a")
check("...again: disconnected", until(lambda: m.bt.snapshot()["busy"] is None and
                                      m.bt.snapshot()["status"] == "Logi K480 is disconnected", 8))
m.press("a")
check("A on it now: connected, without asking", until(lambda: m.bt.snapshot()["status"] == "Logi K480 is connected", 8))
m.press("y")                                        # (straight away: it said so once it was done)
check("Y: asked first", m.msg == "Press Y again to forget it")
m.press("y")
check("...again: forgotten, gone from the list", until(lambda: m.bt.snapshot()["status"] == "Forgot Logi K480"
                                                          and m.bt.snapshot()["busy"] is None, 8)
      and "Logi K480" not in [r[1] for r in m.settings_rows()])
check("...the pick moved to the row nearest where it was", m.settings_rows()[m.bt_sel(m.settings_rows())][0]
      in ("bt_dev", "bt_new", "bt_power"))

# ---- off (asked twice) and on ----------------------------------------------------------------
m.bt_pick = None
m.press("right")
check("◀▶ on the switch: asked first", "turn Bluetooth off" in (m.msg or "") and m.bt.snapshot()["on"])
m.press("right")
check("...again: off; only the switch left, and a word on why", until(lambda: not m.bt.snapshot()["on"], 6)
      and [k for k, _, _ in m.settings_rows()] == ["bt_power"]
      and "Turn it on to connect your controllers, keyboards and headphones" in drawn())
shot("off")
until(lambda: m.bt.snapshot()["busy"] is None, 4)   # (as a person would: it's done, then A)
m.press("a")
check("A: on again, without asking, and looking", until(lambda: m.bt.snapshot()["on"] and m.bt.snapshot()["looking"], 6))

# ---- B: back, and it lets go -----------------------------------------------------------------
m.press("b")
check("B: Settings' first page, on Bluetooth's row", m.set_page == "root"
      and m.settings_rows()[m.set_sel][0] == "bluetooth")
check("...done looking, bluetoothctl closed", until(lambda: not m.bt.snapshot()["looking"] and not m.bt.agent.alive(), 6))
m.press("a")
check("back in: looking again", until(lambda: m.bt.snapshot()["looking"], 3))
m.switch_tab(-1)
check("another tab: it lets go too", until(lambda: not m.bt.agent.alive(), 6))

# ---- no Bluetooth --------------------------------------------------------------------------
F.change(lambda st: st.update(running=False))
m.open_app(si)
m.set_page = "root"
m.set_sel = [k for k, _, _ in m.settings_rows()].index("bluetooth")
m.bt.looked = 0.0
check("no Bluetooth: its row says so", until(lambda: "Not on this Pi" in drawn(), 4))
m.press("a")
check("...its page says why", until(lambda: "Bluetooth isn't running on this Pi" in drawn(), 4))
shot("none")
m.press("b")
ImageDraw.ImageDraw.text = real_text
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
