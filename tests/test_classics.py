import io, os, sys, time, shutil, urllib.parse, json
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image
S = SP + "/t27"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
asked = []
net = {"down": False}
def fake_json(url, timeout=15):
    asked.append((url, timeout))
    if net["down"]:
        raise OSError("timed out")
    ident = urllib.parse.unquote(urllib.parse.urlparse(url).path.split("/")[-1])
    if ident == "MorePopeyeCartoons":       # several cartoons in one item
        files = []
        for stem in ("ADateToSkate", "SpookySwabs"):
            files += [{"name": stem + ".mpeg", "source": "original", "size": "200000000"},
                      {"name": stem + "_512kb.mp4", "source": "derivative", "original": stem + ".mpeg", "size": "20000000"},
                      {"name": stem + ".mp4", "source": "derivative", "original": stem + ".mpeg", "size": "60000000"}]
        return {"files": files}
    if ident == "littlelulu-publicdomain":
        return {"files": [{"name": "Super Lulu (1947).mp4", "source": "original", "size": "300000000"},
                          {"name": "Super Lulu (1947).ia.mp4", "source": "derivative", "original": "Super Lulu (1947).mp4", "size": "40000000"},
                          {"name": "Cad and Caddy (1947).ia.mp4", "source": "derivative", "original": "Cad and Caddy (1947).mp4", "size": "1"}]}
    if ident == "renamed_item":
        return {"files": [{"name": "new_name_512kb.mp4", "source": "derivative", "original": "new_name.mpeg", "size": "9"},
                          {"name": "new_name.mpeg", "source": "original", "size": "99"}]}
    return {"files": []}
g.fetch_json = fake_json
CH = [("Anime All Day", "Animation"), ("Naruto", "Kids"), ("Retro Toons", "Kids"), ("Popeye Channel", "Classic TV"),
      ("Action Movies", "Movies")]
CHANNELS = [{"title": t, "key": f"/ch/{i}", "thumb": "", "genre": gen} for i, (t, gen) in enumerate(CH)]
plex = {"n": 0, "fail": False, "slow": 0}
def live_channels(self):
    plex["n"] += 1
    time.sleep(plex["slow"])
    if plex["fail"]:
        raise OSError("no wifi")
    return CHANNELS
g.Plex.live_channels = live_channels
spawned = []
class Proc:
    stdin = io.StringIO()
    code = None
    def poll(self): return Proc.code
    def kill(self): pass
    def wait(self, timeout=None): return 0
def fake_spawn(self, args, target):
    spawned.append((args, target)); self.proc = Proc(); self.started = time.monotonic()
g.Media.spawn = fake_spawn
class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def close(self): pass
g.Framebuffer = FB
shots = {}
def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last
def wait_for(c, t=8):
    e = time.time() + t
    while time.time() < e:
        m.tick()
        if c(): return True
        time.sleep(0.05)
    return False
def titles(): return [x["title"] for x in m.tab_items()]

m = g.Media(); m.enter()
m.home_sel = [a for a, _ in m.home_apps()].index("TV"); m.press("a"); tv = m.tab
m.sels[tv] = titles().index("Cartoons"); m.press("a"); ci = m.tab
print("root, at once:", m.status.get(ci), "| rows:", [(x["title"], x["sub"]) for x in m.tab_items()][:6], "…", len(titles()))
print("asked anything:", asked, "| asked Plex:", plex["n"])
snap("root")
m.sels[ci] = titles().index("Popeye"); m.press("a")
print("Popeye:", len(titles()), titles()[:3], "| right side:", m.row_right(m.tab_items()[0])[0], "| hints:", m.list_hints()[0])
snap("popeye")
# play "A Date to Skate": several cartoons in one item -> its own lightest copy
m.sels[ci] = titles().index("A Date to Skate"); m.press("a")
print("plays:", spawned[-1][1], "| metadata timeout:", asked[-1][1])
shots["curtain"] = FB.last
m.press("start"); print("START -> next:", m.cur["title"], spawned[-1][1].split("/")[-1])
m.press("b"); m.proc = None
n = len(asked); m.sels[ci] = titles().index("A Date to Skate"); m.press("a")
print("second time, no lookup:", len(asked) == n); m.press("b"); m.proc = None
# a quick failure: a message, not a run through the whole folder
m.sels[ci] = titles().index("Spooky Swabs"); m.press("a"); m.started = time.monotonic() - 1; Proc.code = 1
m.tick(); Proc.code = None
print("quick failure ->", m.view, "| playing:", m.proc, "| toast:", m.msg)
m.press("b"); print("B ->", titles()[m.sels[ci]] if m.chan_stack.get(ci) else "?", "| root sel:", titles()[m.sels[ci]])
# Little Lulu: original .mp4 listed, the .ia.mp4 copy is lighter
m.sels[ci] = titles().index("Casper & friends"); m.press("a")
m.sels[ci] = titles().index("Little Lulu: Super Lulu"); m.press("a")
print("Lulu plays:", urllib.parse.unquote(spawned[-1][1].split("/")[-1]))
m.press("b"); m.proc = None; m.press("b")
# Archive down: the file listed is used
net["down"] = True
print("down ->", g.ia_best("Popeye_Nearlyweds", "Popeye_Nearlyweds_512kb.mp4"))
net["down"] = False
print("renamed ->", g.ia_best("renamed_item", "old_name_512kb.mp4"))
print("not cached after a miss:", "https://archive.org/download/Popeye_Nearlyweds/Popeye_Nearlyweds_512kb.mp4" not in g.IA_URLS)
# search
m.sels[ci] = 0; m.press("a")
for ch in "popeye": m.keyboard_key("char", ch)
m.press("start"); print("search 'popeye':", len(titles()), "| last:", titles()[-1])
m.press("b")
m.sels[ci] = 0; m.press("a")
for ch in "tom jerry": m.keyboard_key("char", ch)
m.press("start"); print("search 'tom jerry':", titles())
snap("search"); m.press("b")
# Anime without Plex
m.sels[ci] = titles().index("Anime"); m.press("a")
print("anime, not signed in:", m.status.get(ci), m.list_hints()[0]); snap("noplex")
m.press("b")
# signed in, slow Plex: loading then filled
m.plex.cfg.update(token="ACCOUNT"); plex["slow"] = 0.4
m.sels[ci] = titles().index("Anime"); m.press("a"); print("anime:", m.status.get(ci))
assert wait_for(lambda: m.status.get(ci) is None and m.tab_items())
print("anime filled:", titles())
m.press("b"); m.sels[ci] = titles().index("Cartoon channels"); m.press("a")
print("cartoon channels (cached):", titles())
m.press("b")
# Plex fails -> error -> A again
m.plex_live = (0.0, []); plex["fail"] = True; plex["slow"] = 0
m.sels[ci] = titles().index("Anime"); m.press("a")
assert wait_for(lambda: m.status.get(ci) == "error"); print("error hints:", m.list_hints()[0])
plex["fail"] = False; m.press("a")
assert wait_for(lambda: m.status.get(ci) is None and m.tab_items()); print("after A:", titles(), "| depth:", len(m.chan_stack[ci]))
m.press("b"); m.press("b"); print("B B ->", g.LIBRARY[m.tab]["name"])
# B while loading: the late answer doesn't land on the root
m.plex_live = (0.0, []); plex["slow"] = 0.5
m.sels[m.tab] = titles().index("Cartoons"); m.press("a")
m.sels[ci] = titles().index("Anime"); m.press("a"); m.press("b")
time.sleep(0.8); m.tick(); print("root after a late answer:", m.status.get(ci), titles()[:2])
print("archive searches:", [u for u, _ in asked if "advancedsearch" in u])
W, H = 640, 480
order = ["root", "popeye", "search", "curtain"]
out = Image.new("RGB", (W * 2 + 10, (H + 10) * 2 - 10), (80, 80, 80))
for k, name in enumerate(order):
    out.paste(shots[name], ((k % 2) * (W + 10), (k // 2) * (H + 10)))
out.save(SP + "/out/classics.png")
print("done")

print("ALL OK")   # (got here: every assert above held)
