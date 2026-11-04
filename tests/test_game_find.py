"""START on the Games tab: a box to find a game by name (not Now playing, there): every word typed in its name, or
its console's ("gba", "game boy"), accents and punctuation or not ("pokemon" finds Pokémon, "pacman" Pac-Man); those
starting with it first, the first picked; what you typed above the list, with how many; nothing found: a word on it.
START again: the box with what you typed, to change; Done with nothing, or B: all of them again, the one you were on
still picked; B again: home. Snake is found too. L R or home: not finding any more. Its footer: START Search, B All
games; its Controls page has START, every row of it on the screen."""
import json, os, shutil, sys, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato.screens.games import fold, game_matches
sys.modules["pitato.screens.games"].GAMES_FLAT = 100   # (one list of them all, as this is about: test_games_org has
                                                       # the folders a long list has)

S = SP + "/t_game_find"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
G = HOME + "/Games"
NAMES = {"gba": ["Pokemon - Emerald Version (USA, Europe)", "Mario Kart - Super Circuit (USA)", "Metroid Fusion (USA)",
                 "Super Mario Advance 4 - Super Mario Bros. 3 (USA)"],
         "nes": ["Super Mario Bros. (World)", "Pac-Man (USA) (Namco)", "Mega Man 2 (USA)", "Tetris (USA)", "Contra (USA)"],
         "snes": ["Super Mario World (USA)", "Super Metroid (Japan, USA) (En,Ja)", "Donkey Kong Country (USA)"],
         "gb": ["Tetris (World) (Rev 1)", "Kirby's Dream Land (USA, Europe)"],
         "gbc": ["Pokémon - Crystal Version (USA, Europe)"]}
EXT = {"gba": ".gba", "nes": ".nes", "snes": ".sfc", "gb": ".gb", "gbc": ".gbc"}
for key, names in NAMES.items():
    os.makedirs(f"{G}/{key}", exist_ok=True)
    for n in names:
        open(f"{G}/{key}/{n}{EXT[key]}", "wb").write(b"\0" * 1024)
os.makedirs(HOME + "/Music")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.PROG_TTY = os.devnull
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): self.show(img)
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


# ---- matching, on its own -----------------------------------------------------------------------
check(f"names folded: lower case, no accents, punctuation spaces ({fold('Pokémon - Crystal (USA)')!r})",
      fold("Pokémon - Crystal (USA)") == "pokemon crystal usa" and fold(None) == "" and fold(" ,.- ") == "")
row = {"kind": "game", "title": "Pac-Man (USA) (Namco)", "label": "Pac-Man", "sub": "NES", "icon": "NES"}
check("every word, with spaces or without: 'pac man', 'pacman', 'man pac', 'nes pac'",
      all(game_matches(row, fold(q).split()) for q in ("pac man", "pacman", "man pac", "nes pac")))
check("...not a word it hasn't: 'pac woman', 'snes'", not game_matches(row, fold("pac woman").split())
      and not game_matches(row, ["snes"]))
snake = {"kind": "child", "title": "Snake", "sub": "Eat the apples, don't crash", "icon": ""}
check("Snake: by its name, not the words about it", game_matches(snake, ["snake"]) and not game_matches(snake, ["apples"]))

# ---- on the Games tab ------------------------------------------------------------------------
g.Framebuffer = FB
m = g.Media(); m.enter()
m.keyreader.start = m.keyreader.stop = lambda: None   # (a real keyboard's typing: not this test's)
gi = m.tab_index("games")
m.open_app(gi)
allrows = m.tab_items()
check(f"the Games tab: Snake and the games ({len(allrows)})", len(allrows) == 1 + sum(map(len, NAMES.values())))


def labels():
    return [it.get("label") or it["title"] for it in m.tab_items()]


def find(text):
    m.press("start")
    m.kb["text"] = ""
    for ch in text:
        m.keyboard_key("char", ch)
    m.keyboard_key("done")


def flush():
    m.dirty = True; m.flush()


m.view = "now"; m.kind = "audio"; m.proc = types.SimpleNamespace(poll=lambda: None)   # (music on: START was
m.view = "list"                                                                         # Now playing in lists)
m.sels[gi] = 3
m.press("start")
check(f"START: a box to find a game in, empty, not Now playing ({m.view}, {m.kb and m.kb['title']!r})",
      m.view == "keys" and m.kb["title"] == "Find a game" and m.kb["text"] == "")
m.press("b")
check(f"...B: closed, nothing changed ({m.view}, {len(m.tab_items())})", m.view == "list" and len(m.tab_items()) == len(allrows))
find("mario")
check(f"'mario': the Marios, those starting with it first, the first picked ({labels()}, {m.sels[gi]})",
      labels() == ["Mario Kart - Super Circuit", "Super Mario Advance 4 - Super Mario Bros. 3", "Super Mario Bros.",
                   "Super Mario World"] and m.sels[gi] == 0 and m.view == "list")
flush()
check("...what you typed above the list (the list a row lower)", m.list_top() == m.LIST_TOP + 28 and m.games_q == "mario")
hints = m.list_hints()
check(f"...its footer: A, SELECT (a favourite), Y, B All games, START Search (no Now playing, no L R; X too, if "
      f"there's room) ({hints})", [h[0] for h in hints if h[0] != "X"] == ["A", "SELECT", "Y", "B", "START"]
      and ("B", "All games") in hints
      and ("START", "Search") in hints and all(h[1] != "Now playing" for h in hints))
m.press("down")
picked = m.tab_items()[m.sels[gi]]["key"]
m.press("start")
check(f"START again: the box with what you typed ({m.kb['text']!r})", m.view == "keys" and m.kb["text"] == "mario")
m.kb["text"] = ""
m.keyboard_key("done")
keys = [it["key"] for it in m.tab_items()]
check(f"...Done with nothing: all of them again, the one you were on still picked ({len(keys)})",
      len(keys) == len(allrows) and keys[m.sels[gi]] == picked and m.games_q is None and m.list_top() == m.LIST_TOP)
check(f"...its footer: B Home, START Search ({m.list_hints()})", ("B", "Home") in m.list_hints()
      and ("START", "Search") in m.list_hints())
find("pokemon")
check(f"'pokemon': Pokémon too, accents or not ({labels()})",
      labels() == ["Pokemon - Emerald Version", "Pokémon - Crystal Version"])
find("game boy")
check(f"'game boy': the Game Boy, Color and Advance games ({labels()})",
      sorted(labels()) == sorted(["Pokemon - Emerald Version", "Mario Kart - Super Circuit", "Metroid Fusion",
                                  "Super Mario Advance 4 - Super Mario Bros. 3", "Tetris (World) (Rev 1)",
                                  "Kirby's Dream Land", "Pokémon - Crystal Version"]))
find("snes")
check(f"'snes': the SNES ones, not the NES ones ({labels()})",
      sorted(labels()) == ["Donkey Kong Country", "Super Mario World", "Super Metroid"])
find("nes")
check(f"'nes': the NES ones, not the SNES ones ({labels()})",
      sorted(labels()) == ["Contra", "Mega Man 2", "Pac-Man", "Super Mario Bros.", "Tetris (USA)"])
find("pacman")
check(f"'pacman': Pac-Man ({labels()})", labels() == ["Pac-Man"])
find("snake")
check(f"'snake': Snake ({labels()})", labels() == ["Snake"])
find("TETRIS gb")
check(f"two words, any case: 'TETRIS gb' ({labels()})", labels() == ["Tetris (World) (Rev 1)"])
find("zelda")
rows = m.tab_items()
check(f"nothing has it: a word on that, nothing to play ({rows[0]['title']!r})",
      len(rows) == 1 and rows[0]["kind"] == "info" and "zelda" in rows[0]["title"])
flush()
check(f"...its footer: no A, no Y ({m.list_hints()})", [h[0] for h in m.list_hints()] == ["X", "B", "START"])
m.press("a")
check("...A: nothing", m.view == "list" and m.game is None)

# B: all of them again; B again: home
find("metroid")
m.press("down")
picked = m.tab_items()[m.sels[gi]]["key"]
m.press("b")
keys = [it["key"] for it in m.tab_items()]
check(f"B: all of them again, the one you were on still picked ({m.view})",
      m.view == "list" and m.games_q is None and len(keys) == len(allrows) and keys[m.sels[gi]] == picked)
m.press("b")
check(f"...B again: home ({m.view})", m.view == "home")

# finding one, then: a game played and over, Snake and back, L R, home
m.open_app(gi)
find("tetris")
m.load_tab(gi)                                         # (as a game ending does)
check(f"a game over (the list again): still the ones found ({labels()})", m.games_q == "tetris"
      and sorted(labels()) == ["Tetris (USA)", "Tetris (World) (Rev 1)"])
find("snake")
m.press("a")
check(f"Snake, from what's found ({g.LIBRARY[m.tab]['name']})", g.LIBRARY[m.tab].get("sim") == "snake")
m.press("b")
check(f"...B: back to what's found ({m.tab == gi}, {labels()})", m.tab == gi and labels() == ["Snake"])
m.press("r")
check(f"R: another tab, not finding any more ({g.LIBRARY[m.tab]['name']}, {m.games_q})", m.tab != gi and m.games_q is None)
m.press("l")
check(f"...L, back on Games: all of them ({len(m.tab_items())})", m.tab == gi and len(m.tab_items()) == len(allrows))
find("kirby")
m.go_home()
m.open_app(gi)
check(f"home and back: all of them ({len(m.tab_items())})", m.games_q is None and len(m.tab_items()) == len(allrows))

# its Controls page: START there, every row on the screen
drawn = []
real_key = m.key
m.key = lambda d, x, y, label, on=False: (drawn.append(label), real_key(d, x, y, label, on))[1]
m.press("x")
flush()
m.key = real_key
shot = FB.last.convert("RGB")
bg = shot.getpixel((630, m.fb.h - m.FOOTER - 10))
ink = [any(shot.getpixel((x, y)) != bg for x in range(98, 300)) for y in range(m.LIST_TOP + 30, m.fb.h - m.FOOTER)]
bands = sum(1 for i, v in enumerate(ink) if v and (i == 0 or not ink[i - 1]))
want = 7 + (2 if g.slow_pi() else 3)                  # (A Y START L R B, two lines on the folder, its folders)
check(f"Controls: START on it ({drawn[:6]}), and all {want} rows of it above the footer ({bands})",
      drawn[:5] == ["A", "Y", "START", "L R", "B"] and bands == want)
m.press("x")
m.leave()                                              # (this machine's console as it was: in text mode)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED", flush=True)
