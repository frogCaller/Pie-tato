"""Achievements, in media mode: signing in to RetroAchievements on the web page (a pretend one here: a wrong password
said so, the right one keeps its key, not the password, in a private file the web page never shows; Sign out takes it
off); a game started with your account handed to its process (not on its command line); its counts heard; the game's
menu with Achievements in it (how many are yours) only when it has some; A on it: their list over the game, scrolled,
B back to the menu; a DS game's longer menu still fitting. Its pictures saved, to look at."""
import json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tcheevos_ui"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Games")
os.makedirs(S + "/static")
os.environ["PITATO_STATIC"] = S + "/static"
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import cheevos as CV, games as GM
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=10):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


# ---- a pretend RetroAchievements ---------------------------------------------------------------------------------
asked = []


class RA(BaseHTTPRequestHandler):
    def do_POST(self):
        form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        asked.append((self.path, {k: v[0] for k, v in form.items()}, self.headers.get("User-Agent")))
        if form.get("r") == ["login2"] and form.get("u") == ["frog"] and form.get("p") == ["right one"]:
            code, out = 200, {"Success": True, "User": "Frog", "Token": "k3y-0f-th1s-p1", "Score": 10,
                              "SoftcoreScore": 5, "Messages": 0, "Permissions": 1, "AccountType": "Registered"}
        else:
            code, out = 401, {"Success": False, "Status": 401, "Code": "invalid_credentials",
                              "Error": "Invalid User/Password combination. Please try again."}
        data = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), RA)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["PITATO_RA_HOST"] = f"http://127.0.0.1:{srv.server_address[1]}"


class FB:
    w, h, same = 640, 480, True

    def __init__(self):
        self.last = None

    def show(self, img):
        self.last = img.copy()

    def show_part(self, img, box):
        self.show(img)

    def invalidate(self):
        pass

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()


def section(key):
    return next(s for s in m.web_settings_now()["sections"] if s["id"] == key)


sec = section("cheevos")
check(f"the web page's settings: Achievements, a form to sign in ({[r['kind'] for r in sec['rows']]})",
      sec["title"] == "Achievements" and sec["rows"][0]["kind"] == "form" and sec["rows"][0]["key"] == "ra_add"
      and [f["name"] for f in sec["rows"][0]["fields"]] == ["user", "password"] and sec["rows"][0]["fields"][1]["secret"])
said = m.web_settings_do({"key": "ra_add", "value": {"user": "frog", "password": ""}})
check(f"...no password: said so ({said})", said.get("error"))
said = m.web_settings_do({"key": "ra_add", "value": {"user": "frog", "password": "wrong"}})
check(f"...a wrong one: asked of it on a thread of its own, busy meanwhile ({said}, {m.ra_said})",
      said == {"ok": True})
until(lambda: m.ra_said and m.ra_said[0] is False)
row = section("cheevos")["rows"][0]
check(f"...then said so, on the form ({row.get('status')!r}, {row.get('tone')})", row.get("tone") == "bad"
      and "didn't take" in row.get("status", "") and CV.ra_account() is None)
check(f"...asked as RetroAchievements wants: login2, by POST, saying who's asking ({asked[-1]})",
      asked[-1][0] == "/dorequest.php" and asked[-1][1] == {"r": "login2", "u": "frog", "p": "wrong"}
      and asked[-1][2].startswith("Pietato/"))
said = m.web_settings_do({"key": "ra_add", "value": {"user": "frog", "password": "right one"}})
until(lambda: CV.ra_account() is not None)
path = S + "/static/retroachievements.txt"
text = open(path).read()
check(f"the right one: its key kept, with the user as it has it; not the password ({CV.ra_account()})",
      CV.ra_account() == ("Frog", "k3y-0f-th1s-p1") and "right one" not in text and m.ra_said is None)
check(f"...in a file only you can read ({oct(os.stat(path).st_mode & 0o777)}), that the web page never shows",
      os.stat(path).st_mode & 0o777 == 0o600 and g.web_private("retroachievements.txt")
      and "retroachievements.txt" in __import__("pitato.webui", fromlist=["x"]).PRIVATE)
rows = section("cheevos")["rows"]
check(f"...the page: signed in as Frog, and Sign out ({[(r['key'], r.get('value')) for r in rows]})",
      rows[0]["kind"] == "info" and rows[0]["value"] == "Frog" and rows[1]["key"] == "ra_forget")

# a game started: your account handed to its process, not on its command line
seen = {}


class Popen:
    def __init__(self, cmd, env=None, **k):
        seen["cmd"], seen["env"] = cmd, env
        self.stdout, self.stdin = iter(()), open(os.devnull, "w")

    def wait(self, timeout=None):
        return 0


real = GM.subprocess.Popen
GM.subprocess.Popen = Popen
run = GM.GameRun({"path": HOME + "/Games/x.gb", "title": "x", "system": "gb"})
run.start("/nowhere/core.so", sound="")
check("a game's process: your account in its environment, not its command line",
      seen["env"].get("PITATO_RA") == "Frog\nk3y-0f-th1s-p1\n4" and not any("k3y" in c for c in seen["cmd"]))
run = GM.GameRun({"path": HOME + "/Games/x.gb", "title": "x", "system": "gb"})
run.start("/nowhere/core.so", sound="", cheevos=False)
check("...not asked for: not there", "PITATO_RA" not in seen["env"])
run = GM.GameRun({"path": HOME + "/Games/x.wbfs", "title": "x", "system": "wii"})
run.start("/nowhere/core.so", sound="")
check("...a kind of game RetroAchievements has none for (a Wii's): not there", "PITATO_RA" not in seen["env"])
GM.subprocess.Popen = real

# ---- the game's menu ----------------------------------------------------------------------------------------------
LIST = {"head": "3 of 24 yours: 45 of 300 points",
        "list": [{"title": "First Blood", "description": "Beat the first boss", "points": 10, "unlocked": True,
                  "progress": ""},
                 {"title": "Collector", "description": "Get 10 rings in one go", "points": 5, "unlocked": False,
                  "progress": "3/10"}]
        + [{"title": f"Number {k}", "description": f"Do thing {k}", "points": k, "unlocked": k < 3, "progress": ""}
           for k in range(1, 23)]}


class Run:
    def __init__(self, system, cheevos):
        self.game = {"path": HOME + "/Games/x", "title": "Sonic Adventure", "system": system}
        self.cheevos, self.state, self.ended, self.slow, self.disc, self.asks = cheevos, "on", False, False, (0, 1), []

    def ask(self, line, wants, timeout=3):
        self.asks.append(line)
        if line.startswith("cheevolist "):
            json.dump(LIST, open(line.split(" ", 1)[1], "w"))
            return "cheevolist", "ok"
        return None, ""

    def resume(self):
        pass

    def pause(self):
        return True


m.game = Run("genesis", None)
m.view, m.game_menu = "gamemenu", {"sel": 0, "confirm": (None, 0.0), "bg": None}
check(f"a game with no achievements (or not signed in): none in its menu ({[j for j, _ in m.game_menu_items()]})",
      "cheevos" not in [j for j, _ in m.game_menu_items()])
m.game.cheevos = (3, 24)
items = [j for j, _ in m.game_menu_items()]
check(f"...with some: Achievements, before Quit, how many are yours ({m.game_value('cheevos')})",
      items[-2:] == ["cheevos", "quit"] and m.game_value("cheevos") == "3 of 24")
m.game_menu["sel"] = items.index("cheevos")
m.dirty = True; m.flush()
m.fb.last.save(S + "/menu.png")
m.press("a")
lst = m.game_menu.get("list")
check(f"A: their list, over the game ({lst and len(lst['rows'])}, asked {m.game.asks})",
      lst is not None and len(lst["rows"]) == 24 and m.game.asks[-1].startswith("cheevolist ")
      and not os.path.exists(m.game.asks[-1].split(" ", 1)[1]))
m.dirty = True; m.flush()
m.fb.last.save(S + "/list.png")
for _ in range(9):
    m.press("down")
m.press("right")
m.dirty = True; m.flush()
m.fb.last.save(S + "/list2.png")
check(f"...down, and ▶ a page at a time ({lst['sel']}, from {lst['top']})", lst["sel"] == 14 and lst["top"] > 0)
m.press("b")
check("...B: back to the menu, still on Achievements", m.game_menu.get("list") is None and m.view == "gamemenu"
      and m.game_menu_items()[m.game_menu["sel"]][0] == "cheevos")

# a DS game's menu, Achievements and all: it fits
m.game = Run("nds", (1, 40))
m.game_menu = {"sel": 0, "confirm": (None, 0.0), "bg": None}
n = len(m.game_menu_items())
m.dirty = True; m.flush()
img = m.fb.last
m.fb.last.save(S + "/ds-menu.png")
above = img.crop((0, 480 - 48 - 6, 640, 480 - 48)).convert("L")           # (just above the buttons: the menu's
check(f"a DS game's menu ({n} rows, Achievements too): all of it above the buttons along the bottom",   # edge isn't)
      n == 11 and max(above.tobytes()) < 40)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
srv.shutdown()
