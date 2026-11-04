"""The Games tab with a lot of games: a dozen or fewer, one list as before; more, a folder for each console (in order),
All games, and once there are some, Recently played (the last first) and Favourites (SELECT on a game); a folder's
games A to Z, ◀▶ by letter, B back out with its folder picked; START finds a game in all of them, B back to the
folder; home shuts it; a folder's picture one of its games'; Y finds pictures for every game from the top; the web
page's settings: the consoles you have games for, in order. Its pictures saved, to look at."""
import os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image
S = SP + "/tgamesorg"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
os.makedirs(GAMES + "/Images")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


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


def put(name, size=32768):
    os.makedirs(os.path.dirname(f"{GAMES}/{name}"), exist_ok=True)
    open(f"{GAMES}/{name}", "wb").write(bytes(size))


def titles():
    return [r.get("label") or r["title"] for r in m.tab_items()]


def shot(name):
    m.dirty = True
    m.flush()
    m.fb.last.save(f"{S}/{name}.png")


# ---- a few: one list, as it was --------------------------------------------------------------------------------------
for n in ("Tetris (World).gb", "Kirby's Dream Land (USA).gb", "Metroid Fusion (USA).gba", "Contra (USA).nes",
          "Super Metroid (USA).sfc"):
    put(n)
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
m.view = "home"
apps = [a for a, _ in m.home_apps()]
m.home_sel = apps.index("Games")
m.press("a")
check(f"five games: Snake, then all of them in one list, as before ({titles()})", m.tab_type() == "games"
      and titles() == ["Snake", "Contra", "Kirby's Dream Land", "Metroid Fusion", "Super Metroid", "Tetris"]
      and not m.games_dir and all(r["kind"] in ("child", "game") for r in m.tab_items()))
m.sels[m.tab] = 1
m.press("right")
check(f"...◀▶ page through it, as before ({m.sels[m.tab]})", m.sels[m.tab] == 5)

# ---- a lot of games: a folder for each console --------------------------------------------------------------------
for n in ("Asteroids (USA).gb", "Bomberman GB (USA).gb", "Dr. Mario (World).gb", "Wario Land (USA).gb",
          "Advance Wars (USA).gba", "Golden Sun (USA).gba", "Mario Kart - Super Circuit (USA).gba",
          "Metroid - Zero Mission (USA).gba", "Minish Cap (USA).gba", "Pokemon Emerald (USA).gba",
          "Wario Ware (USA).gba", "1942 (USA).nes", "Balloon Fight (USA).nes", "Castlevania (USA).nes",
          "Double Dragon (USA).nes", "Dr. Mario (USA).nes", "Mega Man 2 (USA).nes", "Zelda (USA).nes",
          "Chrono Trigger (USA).sfc", "Donkey Kong Country (USA).sfc", "F-Zero (USA).sfc", "Star Fox (USA).sfc",
          "Sonic the Hedgehog (USA).md", "Streets of Rage 2 (USA).md", "Gunstar Heroes (USA).md",
          "Ecco the Dolphin (USA).md"):
    put(n)
Image.new("RGB", (64, 64), (200, 40, 40)).save(f"{GAMES}/Images/Golden Sun (USA).png")    # (a GBA game's box)
Image.new("RGB", (64, 64), (40, 40, 200)).save(f"{GAMES}/Images/Contra (USA).png")
m.load_tab(m.tab)
rows = m.tab_items()
check(f"31 games: Snake, a folder for each console in order, then All games ({titles()})",
      titles() == ["Snake", "Game Boy", "Game Boy Advance", "NES", "SNES", "Genesis / Mega Drive", "All games"]
      and all(r["kind"] == "gamedir" for r in rows[1:]))
by = {r["title"]: r for r in rows}
check(f"...each one's badge and how many ({[(r['icon'], r['sub']) for r in rows[1:]]})",
      [(r["icon"], r["sub"]) for r in rows[1:]] == [("GB", "6 games"), ("GBA", "8 games"), ("NES", "8 games"),
                                                    ("SNES", "5 games"), ("MD", "4 games"), ("ALL", "31 games")]
      or [r["sub"] for r in rows[1:]] == ["6 games", "8 games", "8 games", "5 games", "4 games", "31 games"])
check(f"...a folder's picture: one of its games' (the GBA's: Golden Sun's; the NES's: Contra's; none for the GB's)",
      by["Game Boy Advance"]["cover"].endswith("Golden Sun (USA).gba") and by["NES"]["cover"].endswith("Contra (USA).nes")
      and by["Game Boy"]["cover"] is None and m.game_pic(by["Game Boy Advance"], "panel") is not None
      and m.game_pic(by["Game Boy Advance"], "thumb") is None and m.game_pic(by["Game Boy"], "panel") is None)
m.sels[m.tab] = 2
shot("top")
hints = m.list_hints()
check(f"...drawn; A opens a folder, B home, START searches, Y finds pictures ({hints})", hints[0] == ("A", "Open")
      and ("START", "Search") in hints and ("Y", "Find pictures") in hints and ("B", "Home") in hints
      and not any(h[0] == "SELECT" for h in hints))
m.press("a")
check(f"A on Game Boy Advance: its games, A to Z, the first picked ({titles()})", m.games_dir == "sys:gba"
      and titles() == ["Advance Wars", "Golden Sun", "Mario Kart - Super Circuit", "Metroid - Zero Mission",
                       "Metroid Fusion", "Minish Cap", "Pokemon Emerald", "Wario Ware"] and m.sels[m.tab] == 0)
shot("gba")
hints = m.list_hints()
check(f"...drawn, with where you are; A plays, SELECT stars it, ◀▶ by letter, B back ({hints})",
      hints[0] == ("A", "Play") and ("SELECT", "★") in hints and ("◀▶", "A–Z") in hints and ("B", "Back") in hints
      and m.list_top() > m.LIST_TOP)
m.press("right")
check(f"▶: the next letter's first ({titles()[m.sels[m.tab]]})", titles()[m.sels[m.tab]] == "Golden Sun")
m.press("right")
check(f"...and the next ({titles()[m.sels[m.tab]]})", titles()[m.sels[m.tab]] == "Mario Kart - Super Circuit")
m.press("down")
check(f"(down a row: {titles()[m.sels[m.tab]]})", titles()[m.sels[m.tab]] == "Metroid - Zero Mission")
m.press("left")
check(f"◀ in a letter's games: its first ({titles()[m.sels[m.tab]]})", titles()[m.sels[m.tab]] == "Mario Kart - Super Circuit")
m.press("left")
check(f"...again: the letter before's first ({titles()[m.sels[m.tab]]})", titles()[m.sels[m.tab]] == "Golden Sun")
m.sels[m.tab] = 7
m.press("right")
check(f"▶ on the last letter: round to the first ({titles()[m.sels[m.tab]]})", titles()[m.sels[m.tab]] == "Advance Wars")
m.press("left")
check(f"◀ on the first: round to the last letter's first ({titles()[m.sels[m.tab]]})", titles()[m.sels[m.tab]] == "Wario Ware")

# favourites
m.sels[m.tab] = 1
m.press("select")
rows = m.tab_items()
check(f"SELECT: Golden Sun one of your favourites, a star on its row ({rows[1].get('fav')}, {m.setting('games_favourites')})",
      rows[1].get("fav") and m.setting("games_favourites") == [f"{GAMES}/Golden Sun (USA).gba"]
      and titles()[m.sels[m.tab]] == "Golden Sun")
shot("gba-fav")
check(f"...its hint: SELECT takes it out ({[h for h in m.list_hints() if h[0] == 'SELECT']})",
      ("SELECT", "Unstar") in m.list_hints())
m.press("b")
check(f"B: back out, Game Boy Advance picked ({titles()}, {titles()[m.sels[m.tab]]})", not m.games_dir
      and titles()[m.sels[m.tab]] == "Game Boy Advance" and titles()[:2] == ["Snake", "Favourites"])
fav = m.tab_items()[1]
check(f"...Favourites, after Snake ({fav['sub']}, its picture Golden Sun's)", fav["sub"] == "1 game"
      and fav["icon"] == "★" and fav["cover"].endswith("Golden Sun (USA).gba"))
m.sels[m.tab] = 1
m.press("a")
check(f"...in it: Golden Sun ({titles()})", titles() == ["Golden Sun"] and m.games_dir == "fav")
m.press("select")
check(f"...SELECT again: taken out; nothing left ({titles()})", titles() == ["No favourites yet: SELECT on a game adds it"]
      and m.setting("games_favourites") == [])
m.press("b")
check(f"...out: no Favourites folder now ({titles()})", "Favourites" not in titles())

# recently played: a game that starts


class Run:
    def __init__(self, path):
        self.game, self.state, self.ended, self.error = {"path": path, "title": "", "system": ""}, "on", False, ""

    def quit(self, *a):
        self.state = "done"


for name in ("Contra (USA).nes", "Chrono Trigger (USA).sfc", "Contra (USA).nes"):
    m.game = Run(f"{GAMES}/{name}")
    m.game_since = time.monotonic()
    m.game_tick(time.monotonic())
    m.game_tick(time.monotonic())                  # (once, however many ticks)
    m.view = "game"
    m.game_end()
check(f"three games played (Contra twice): the last first, once each ({m.setting('games_recent')})",
      m.setting("games_recent") == [f"{GAMES}/Contra (USA).nes", f"{GAMES}/Chrono Trigger (USA).sfc"])
check(f"...Recently played, first after Snake: the last one's name ({titles()[:2]}, {m.tab_items()[1]['sub']})",
      titles()[:2] == ["Snake", "Recently played"] and m.tab_items()[1]["sub"] == "Contra"
      and m.tab_items()[1]["icon"] == "LAST")
m.sels[m.tab] = 1
m.press("a")
check(f"...in it: the last first ({titles()}); ◀▶ page here, not by letter", titles() == ["Contra", "Chrono Trigger"]
      and not m.games_by_letter())
shot("recent")
m.sels[m.tab] = 1
m.game = Run(f"{GAMES}/Chrono Trigger (USA).sfc")
m.game_tick(time.monotonic())
m.view = "game"
m.game_end()
check(f"...a game played from there: first now, and still picked ({titles()}, {titles()[m.sels[m.tab]]})",
      titles() == ["Chrono Trigger", "Contra"] and titles()[m.sels[m.tab]] == "Chrono Trigger" and m.games_dir == "recent")
os.remove(f"{GAMES}/Chrono Trigger (USA).sfc")
m.load_tab(m.tab)
check(f"...one gone from the Games folder: gone from it too ({titles()})", titles() == ["Contra"])
put("Chrono Trigger (USA).sfc")

# finding a game, from in a folder
m.press("b")
m.sels[m.tab] = titles().index("NES")
m.press("a")
m.games_search("mario")
check(f"START in the NES folder: what you typed, found in all of them ({titles()})", m.games_q == "mario"
      and sorted(titles()) == sorted(["Dr. Mario (World)", "Dr. Mario (USA)", "Mario Kart - Super Circuit"])
      and not m.games_by_letter())
m.press("b")
check(f"...B: back in the NES folder ({titles()[:3]}...)", not m.games_q and m.games_dir == "sys:nes"
      and titles()[:3] == ["1942", "Balloon Fight", "Castlevania"])
shot("nes")

# Y from the top: every game's pictures
m.press("b")
asked = []


class Finder:
    busy, note, total, done = False, "", 0, 0
    on_change = None

    def start(self, games):
        asked.extend(games)
        self.total = len(games)
        return True


m.art_finder = Finder()
m.press("y")
check(f"Y at the top: pictures found for every game, not just the folders ({len(asked)})", len(asked) == 31)

# home shuts the folder; a few games again: one list
m.sels[m.tab] = titles().index("SNES")
m.press("a")
m.go_home()
check("home: the folder shut", m.games_dir is None)
check(f"the web page's settings: the consoles you have games for, in order ({m.games_systems()})",
      m.games_systems() == ["gb", "gba", "nes", "snes", "genesis"])
m.view = "home"
m.home_sel = [a for a, _ in m.home_apps()].index("Games")
m.press("a")
m.sels[m.tab] = titles().index("SNES")
m.press("a")
for n in os.listdir(GAMES):
    if n.endswith((".gba", ".md", ".gb")):
        os.remove(f"{GAMES}/{n}")
m.load_tab(m.tab)
check(f"down to 13 games, in the SNES folder: still folders ({titles()})", m.games_dir == "sys:snes" and len(titles()) == 5)
os.remove(f"{GAMES}/1942 (USA).nes")
m.load_tab(m.tab)
check(f"...12: one list again, the folder gone ({titles()[:3]}...)", m.games_dir is None and len(titles()) == 13
      and titles()[1] == "Balloon Fight")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
