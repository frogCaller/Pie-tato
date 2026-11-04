import os, sys, time, shutil
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image

S = SP + "/t20"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.fetch_json = lambda url: (_ for _ in ()).throw(OSError("offline"))

# a pretend NetworkManager
AIR = [("HomeNet", 82, "WPA2"), ("Cafe:Guest", 64, ""), ("Neighbors 5G", 48, "WPA2 WPA3"),
       ("HomeNet", 40, "WPA2"), ("", 30, "WPA2"), ("Printer-Setup", 20, "")]
PASSWORDS = {"Neighbors 5G": "Tr1cky!pass#", "Secret Lab": "hidden-pass"}
nmstate = {"profiles": {"preconfigured": "HomeNet"}, "active": "HomeNet", "radio": True}
log = []


def fake_nm(args, timeout=20):
    log.append(args)
    p = nmstate["profiles"]
    if args[:2] == ["radio", "wifi"]:
        if len(args) == 3:
            nmstate["radio"] = args[2] == "on"
            if not nmstate["radio"]:
                nmstate["active"] = None
            return True, "", ""
        return True, "enabled\n" if nmstate["radio"] else "disabled\n", ""
    if "device" in args and "list" in args:
        if not nmstate["radio"]:
            return True, "", ""
        out = []
        for ssid, sig, sec in AIR:
            out.append(":".join(["*" if ssid == nmstate["active"] and sig == 82 else " ",
                                 ssid.replace(":", "\\:"), str(sig), sec]))
        return True, "\n".join(out) + "\n", ""
    if args[-2:] == ["connection", "show"]:
        return True, "".join(f"{n}:802-11-wireless\n" for n in p) + "Wired connection 1:802-3-ethernet\n", ""
    if args[:2] == ["-g", "802-11-wireless.ssid"]:
        return True, p[args[-1]] + "\n", ""
    if args[:3] == ["connection", "up", "id"]:
        nmstate["active"] = p[args[3]]
        return True, "Connection successfully activated\n", ""
    if args[:3] == ["device", "wifi", "connect"]:
        ssid = args[3]
        pw = args[args.index("password") + 1] if "password" in args else None
        hidden = "hidden" in args
        if not hidden and ssid not in [a[0] for a in AIR]:
            return False, "", f"Error: No network with SSID '{ssid}' found."
        p[ssid] = ssid
        if PASSWORDS.get(ssid) and pw != PASSWORDS[ssid]:
            return False, "", "Error: Connection activation failed: (7) Secrets were required, but not provided."
        nmstate["active"] = ssid
        return True, f"Device 'wlan0' successfully activated with '{ssid}'.\n", ""
    if args[:3] == ["connection", "delete", "id"]:
        if p.pop(args[3], None) and nmstate["active"] == args[3]:
            nmstate["active"] = None
        return True, "", ""
    return False, "", "unexpected " + " ".join(args)


g.nm = fake_nm
g.run_out = lambda cmd, timeout=3: (f"Connected to aa:bb\n\tSSID: {nmstate['active']}\n"
                                    if cmd[:2] == ["iw", "dev"] and nmstate["active"] else "")
shots = {}


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass


g.Framebuffer = FB


def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last


def wait_idle(t=8):
    e = time.time() + t
    time.sleep(0.05)
    while time.time() < e and m.wifi["busy"]:
        time.sleep(0.05)
    assert not m.wifi["busy"]


def pick(title):
    rows = m.settings_rows()
    m.set_sel = next(k for k, r in enumerate(rows) if r[1] == title)


def type_text(text):
    for ch in text:
        m.keyboard_key("char", ch)


m = g.Media()
m.enter()
m.home_sel = [a[0] for a in m.home_apps()].index("Settings"); m.press("a")
print("settings rows:", [r[1] for r in m.settings_rows()])
snap("settings")
m.set_sel = 0; m.press("a")
print("page:", m.set_page, "| status:", m.wifi["status"])
snap("scanning")
wait_idle()
print("networks:", [(n["ssid"], n["signal"], n["secure"], n["active"]) for n in m.wifi["nets"]])
print("saved:", m.wifi["saved"])
snap("wifi")

# an open network: straight on
pick("Cafe:Guest"); m.press("a"); wait_idle()
print("open ->", nmstate["active"], "| toast:", m.msg)
# a locked one: the keyboard, a wrong password first
pick("Neighbors 5G"); m.press("a")
print("keyboard:", m.view, m.kb["title"])
type_text("wrong pass ")
m.press("start"); wait_idle()
print("wrong ->", nmstate["active"], "| toast:", m.msg, "| broken profile kept:", "Neighbors 5G" in nmstate["profiles"])
pick("Neighbors 5G"); m.press("a")
m.kb["r"], m.kb["c"] = 1, 4; m.press("select"); m.press("a")          # T
m.kb["r"], m.kb["c"] = 1, 3; m.press("a")                             # r
m.kb["r"], m.kb["c"] = 0, 0; m.press("a")                             # 1
type_text("cky")
m.kb["r"], m.kb["c"] = 4, 1; m.press("a")                             # #+=
print("symbols on:", m.kb["sym"])
m.kb["r"], m.kb["c"] = 0, 0; m.press("a")                             # !
m.kb["r"], m.kb["c"] = 4, 1; m.press("a")                             # abc
type_text("pass#")
snap("password")
print("typed:", m.kb["text"])
m.press("start"); wait_idle()
print("right ->", nmstate["active"], "| toast:", m.msg)
snap("connected")
# forget: Y twice
pick("Neighbors 5G"); m.press("y"); print("first Y:", m.msg)
snap("forget_ask")
m.press("y"); wait_idle()
print("forgot:", "Neighbors 5G" not in nmstate["profiles"], "| active now:", nmstate["active"], "| toast:", m.msg)
# back on the saved home network: no password asked
pick("HomeNet"); m.press("a"); wait_idle()
print("saved network ->", nmstate["active"], "| via:", [a for a in log if a[:2] == ["connection", "up"]][-1])
# a hidden network
pick("Other network…"); m.press("a"); type_text("Secret Lab"); m.press("start")
print("then:", m.view, m.kb and m.kb["title"])
type_text("hidden-pass"); m.press("start"); wait_idle()
print("hidden ->", nmstate["active"], "| toast:", m.msg)
# WiFi off and on
m.set_sel = 0; m.press("right"); wait_idle()
print("off:", m.wifi["radio"], "| rows:", [r[1] for r in m.settings_rows()])
snap("off")
m.press("right"); wait_idle()
print("on:", m.wifi["radio"], len(m.wifi["nets"]), "networks")
m.press("b"); print("B ->", m.set_page, "| row:", m.settings_rows()[m.set_sel][1])
m.press("b"); print("B ->", m.view)
# nmcli missing
g.nm = lambda args, timeout=20: (False, "", "nmcli isn't installed (NetworkManager)")
m.home_sel = [a[0] for a in m.home_apps()].index("Settings"); m.press("a"); m.set_sel = 0; m.press("a"); wait_idle()
print("no nmcli:", m.wifi["status"])

W, H = 640, 480
order = ["settings", "wifi", "password", "connected", "forget_ask", "off"]
out = Image.new("RGB", (W * 2 + 10, (H + 10) * 3 - 10), (80, 80, 80))
for k, name in enumerate(order):
    out.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
out.save(SP + "/out/wifi_settings.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
