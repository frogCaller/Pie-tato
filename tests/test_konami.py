"""Konami code (screens/konami.py), in Apps: your own button codes that do things. Its page: the classic code
to start with (▲▲▼▼◀▶◀▶BA: cmatrix), and New code: press it (every button's part of it), stop a moment, then pick what
it does. A code has 3 buttons at least (any of them), isn't one you have and doesn't start like one (said, and put in
again); HOME stops. HOME and ▶ (app.py: test_konami_home) bring up the box for a code, on the home
screen, in a list or Now playing: one of yours, all in, and it's done, back where you were; the start of none of
them, said; given up on after a while; HOME: never mind. Not in a game, over a video, or while one's put in or picked.
None left: said. What a code can do: the TV on or off and the lights on or off (Home Assistant), open an app, a
random song, your last game, the screen off, the home screen. X changes what one does, Y twice forgets it; kept
(and none, kept as none)."""
import os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.screens.konami as K

S = SP + "/t_konami"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves", "Games/nes"):
    os.makedirs(f"{HOME}/{d}")
for song in ("One.mp3", "Two.mp3"):
    open(f"{HOME}/Music/{song}", "wb").write(b"\0" * 64)
ROM = HOME + "/Games/nes/Contra (USA).nes"
open(ROM, "wb").write(b"\0" * 64)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if "dirs" in t:
        t["dirs"] = [x.replace("/home/*", HOME) for x in t["dirs"]]
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): pass
    def invalidate(self): pass
    def close(self): pass


class HA:
    """Home Assistant, for the TV: what it's asked."""
    configured, watch, tvstate = True, None, {}
    def __init__(self): self.sent, self.started, self.stopped = [], 0, 0
    def load(self, files, pick=""): pass
    def send(self, *job): self.sent.append(job)
    def start(self): self.started += 1
    def stop(self): self.stopped += 1
    def busy(self): return False


class Lights:
    """Home Assistant, for the lights: two off and one on, once it's asked."""
    configured, found, error = True, False, None
    def __init__(self): self.rows, self.toggled, self.calls = [], [], []
    def load(self, files): pass
    def refresh(self):
        self.rows = [{"entity": "light.a", "kind": "light", "on": False}, {"entity": "light.b", "kind": "light",
                     "on": False}, {"entity": "light.c", "kind": "light", "on": True}]
        self.found = True
    def lights(self): return self.rows
    def toggle(self, r): self.toggled.append(r["entity"]); r["on"] = not r["on"]
    def all_off(self):
        n = sum(1 for r in self.rows if r["on"])
        for r in self.rows:
            r["on"] = False
        self.calls.append("alloff")
        return n
    def start(self): self.calls.append("start")
    def stop(self): self.calls.append("stop")


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.hass, m.lights = HA(), Lights()
toasts, progs, plays, games, rests = [], [], [], [], []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
m.prog_start = lambda name: progs.append(name)
m.play = lambda queue, i, start=None, show=True, note=None: plays.append(([q["title"] for q in queue], show))
m.game_open = lambda it: games.append(it["src"])
m.rest_start = lambda: rests.append(True)
KI = m.tab_index("konami")
SIMI = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Apps")
MUSIC = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Music")


def press(*names):
    for n in names:
        m.press(n)


def rows():
    return [(it["title"], it["sub"]) for it in m.tab_items(KI)]


def on_page():
    m.go_home()
    m.web_tab("Konami code")


def record(*names, done=True):
    """New code: the buttons, then a moment's stop (one being put in already: HOME stops it first)."""
    m.konami_home()
    on_page()
    m.sels[KI] = len(m.tab_items(KI)) - 1
    press("a")
    press(*names)
    if done and m.konami_rec is not None:
        m.konami_rec["at"] -= K.REC_DONE + 0.1
        m.tick()


def code(*names):
    """HOME and ▶ (the box for a code), then these."""
    ok = m.konami_hotkey_ok() and m.konami_listen()
    press(*names)
    return ok


# ---- Apps', and its page ----------------------------------------------------------------------------------
names = g.LIBRARY[SIMI]["children"]
check(f"Apps: Konami code, after its worlds and before Linux's programs ({names})",
      names.index("Konami code") == names.index("Mandelbrot Set") + 1 and names.index("cmatrix")
      == names.index("Konami code") + 1)
m.tab, m.view = SIMI, "list"
m.load_tab(SIMI)
row = next(it for it in m.tab_items() if it["title"] == "Konami code")
check(f"...its row ({row['icon']}, {row['sub']})", row["icon"] == "CHEAT" and row["sub"] == "Button codes that do things")
m.sels[SIMI] = m.tab_items().index(row)
press("a")
check(f"A: its page: the classic code to start with, then New code ({rows()})", m.tab == KI
      and rows() == [("▲ ▲ ▼ ▼ ◀ ▶ ◀ ▶ B A", "Open cmatrix"), ("New code", "Press it, then pick what it does")])
check(f"...its buttons, and how a code's put in ({m.list_hints()}, {m.konami_note()!r})",
      m.list_hints() == [("A", "Try it"), ("X", "Change"), ("Y", "Forget"), ("B", "Back")]
      and m.konami_note() == "HOME and ▶, then a code")
m.dirty = True; m.flush()
FB.last.save(S + "/page.png")
check("...the bot's \"something cool\" doesn't pick it", "Konami code" not in [t["name"] for t in m.cool_choices()])

# ---- the box for a code: the classic one, from the home screen ------------------------------------------------------
m.go_home()
m.home_sel = 0
check("HOME and ▶: the box for a code (on the home screen; the web page says so)",
      m.konami_hotkey_ok() and m.konami_listen() and m.view == "konami" and m.konami_in["from"] == "home"
      and m.where_text() == "Konami code")
m.dirty = True; m.flush()
FB.last.save(S + "/box.png")
press("up", "up", "down", "down", "left", "right")
check(f"...its buttons so far ({m.konami_in and m.konami_in['keys']})", m.view == "konami"
      and m.konami_in["keys"] == ["up", "up", "down", "down", "left", "right"] and m.home_sel == 0 and not progs)
m.dirty = True; m.flush()
FB.last.save(S + "/box_keys.png")
press("left", "right", "b", "a")
check(f"...all in: cmatrix, from Apps ({progs}, {toasts[-1:]})", progs == ["cmatrix"] and m.konami_in is None
      and g.LIBRARY[m.tab]["name"] == "Apps" and toasts[-1] == "Konami code: Open cmatrix")

# ---- a new one: ▲▲▼◀▼▶A, the TV on ------------------------------------------------------------------------------------
on_page()
m.sels[KI] = 1
press("a")
check("New code: put it in (every button's part of it)", m.konami_rec is not None and m.list_hints() == [("HOME", "Stop")])
check("...HOME and a button aren't the box's meanwhile (HOME stops it, as it goes down)", not m.konami_hotkey_ok())
m.dirty = True; m.flush()
FB.last.save(S + "/record_empty.png")
press("up", "up", "down", "left", "down", "right", "a")
check(f"...its buttons so far ({m.konami_rec['keys']})", m.konami_rec["keys"] == ["up", "up", "down", "left", "down",
                                                                                  "right", "a"])
m.dirty = True; m.flush()
FB.last.save(S + "/record.png")
m.tick()
check("...not yet done while you're pressing", m.konami_rec is not None)
m.konami_rec["at"] -= K.REC_DONE + 0.1
m.tick()
items = m.tab_items(KI)
check(f"...a moment's stop: done, and what it does to pick ({[it['title'] for it in items]})",
      m.konami_rec is None and m.konami_pick is not None and [it["title"] for it in items] == [l for _, l in K.DOES]
      and items[m.sels[KI]]["src"] == "tv:on")
check(f"...its buttons, and the code at the top ({m.list_hints()}, {m.konami_crumb()!r}, {m.konami_note()!r})",
      m.list_hints() == [("A", "Pick"), ("B", "Back")] and m.konami_crumb() == "  ›  ▲ ▲ ▼ ◀ ▼ ▶ A"
      and m.konami_note() == "" and not m.konami_hotkey_ok())
m.dirty = True; m.flush()
FB.last.save(S + "/pick.png")
press("a")
check(f"A: kept ({rows()}, {toasts[-1:]})", m.konami_pick is None and rows()[1] == ("▲ ▲ ▼ ◀ ▼ ▶ A", "Turn the TV on")
      and toasts[-1] == "▲ ▲ ▼ ◀ ▼ ▶ A: Turn the TV on")
check("...in the state file", len(g.json.load(open(g.STATE_FILE))["settings"]["konami"]) == 2)

# ---- put in from a list, and from Now playing --------------------------------------------------------------------
m.web_tab("Music")
m.sels[MUSIC] = 0
check("in a list: HOME and ▶, then the code", code("up", "up", "down", "left", "down", "right", "a"))
check(f"...the TV on, through Home Assistant; back on the list, and A didn't play a song ({m.hass.sent}, {plays})",
      m.hass.sent == [("power", "on")] and m.hass.started == 1 and m.view == "list" and m.tab == MUSIC
      and m.sels[MUSIC] == 0 and not plays and toasts[-1] == "Konami code: Turn the TV on")
m.konami_ha = (time.monotonic() - 4, m.konami_ha[1])
m.tick()
check(f"...Home Assistant asked no more once it's done ({m.hass.stopped})", m.hass.stopped == 1 and m.konami_ha is None)
m.hass.sent.clear()
m.view, m.now_from = "now", "list"
check("Now playing too", code("up", "up", "down", "left", "down", "right", "a") and m.hass.sent == [("power", "on")]
      and m.view == "now")
m.view = "list"

# ---- not one of yours, too slowly, never mind -----------------------------------------------------------------------
m.hass.sent.clear()
m.go_home()
code("up", "up", "down", "right")
check(f"the start of none of them: said, and back ({toasts[-1:]}, {m.view})", m.view == "home" and m.konami_in is None
      and toasts[-1] == "That's not one of your codes" and not m.hass.sent)
code("up", "up")
m.konami_in["at"] -= K.IN_GAP + 0.1
m.tick()
check(f"...the start of one, then a while: said, and back ({toasts[-1:]})", m.view == "home" and m.konami_in is None
      and toasts[-1] == "That's not one of your codes")
toasts.clear()
code()
m.konami_in["at"] -= K.IN_GAP + 0.1
m.tick()
check("...nothing yet: it waits longer for the first", m.view == "konami")
m.konami_in["at"] -= K.IN_FIRST
m.tick()
check("...then back, nothing said", m.view == "home" and m.konami_in is None and not toasts)
code("up")
check("HOME meanwhile: never mind", m.konami_home() is True and m.view == "home" and m.konami_in is None
      and m.konami_home() is False)
code("up")
m.web_tab("Weather")
m.tick()
check("something else on the screen meanwhile (the web page): the box gone", m.konami_in is None and m.view == "list")
m.go_home()
VI = next(i for i, t in enumerate(g.LIBRARY) if t["type"] == "files" and t.get("kind") == "video")
for where, setup in (("in a game", lambda: setattr(m, "view", "game")),
                     ("over a video", lambda: (setattr(m, "view", "list"), setattr(m, "tab", VI),
                                               setattr(m, "proc", object()), setattr(m, "kind", "video"))),
                     ("in the terminal", lambda: setattr(m, "active", False)),
                     ("while the screen rests", lambda: setattr(m, "resting", True))):
    setup()
    check(f"not {where} (HOME is as ever there)", not m.konami_hotkey_ok())
    m.proc = m.kind = None
    m.view, m.active, m.resting = "home", True, False

# ---- what a code can do -----------------------------------------------------------------------------------------------
m.konami_do("tv:off")
check(f"the TV off ({m.hass.sent[-1:]})", m.hass.sent[-1:] == [("power", "off")])
m.konami_do("lights:on")
end = time.time() + 5
while "stop" not in m.lights.calls and time.time() < end:
    time.sleep(0.05)
time.sleep(0.1)
check(f"the lights on: each that's off ({m.lights.toggled}, {m.lights.calls}, {toasts[-1:]})",
      m.lights.toggled == ["light.a", "light.b"] and m.lights.calls == ["start", "stop"] and toasts[-1] == "2 lights on")
m.lights.calls.clear()
m.konami_do("lights:off")
end = time.time() + 5
while "stop" not in m.lights.calls and time.time() < end:
    time.sleep(0.05)
time.sleep(0.1)
check(f"...off ({m.lights.calls}, {toasts[-1:]})", m.lights.calls == ["alloff", "start", "stop"]
      and toasts[-1] == "3 lights off")
m.konami_do("open:Weather")
check(f"open an app ({g.LIBRARY[m.tab]['name']})", m.view == "list" and g.LIBRARY[m.tab]["name"] == "Weather")
m.konami_do("song")
check(f"a random song (where you are: nothing else on the screen; the rest shuffled after it) ({plays[-1:]})",
      plays and sorted(plays[-1][0]) == ["One", "Two"] and plays[-1][1] is False and m.queue_random)
m.set_setting("games_recent", [ROM])
m.konami_do("game")
check(f"your last game ({games})", games == [ROM])
m.konami_do("rest")
check("the screen off", rests == [True])
m.konami_do("home")
check("the home screen", m.view == "home")
m.hass.configured = False
toasts.clear()
m.konami_do("tv:on")
check(f"Home Assistant not set up: said ({toasts[-1:]})", toasts[-1:] == ["Set up Home Assistant first: Settings > Home"])
m.hass.configured = True

# ---- what can't be a code, and what can -----------------------------------------------------------------------------
for keys, said in ((("up", "down"), "A code has 3 buttons at least. Again"),
                   (tuple(K.KONAMI_CLASSIC), "That's your code for Open cmatrix already. Again"),
                   (("up", "up", "down", "down"), "It starts like your code for Open cmatrix: make it different. "
                                                  "Again"),
                   (tuple(K.KONAMI_CLASSIC) + ("start",), "It starts like your code for Open cmatrix: make it different. "
                                                   "Again")):
    record(*keys)
    check(f"{K.glyphs(keys)}: said, and put in again ({m.konami_rec and m.konami_rec['said']!r})",
          m.konami_rec is not None and m.konami_rec["said"] == said and m.konami_rec["keys"] == [])
m.dirty = True; m.flush()
FB.last.save(S + "/record_said.png")
check("HOME: it stops", m.konami_home() is True and m.konami_rec is None and m.konami_home() is False)
record("a", "b", "start")
check(f"any buttons: A B START, a code ({m.konami_pick and m.konami_pick['keys']})", m.konami_rec is None
      and m.konami_pick is not None and m.konami_pick["keys"] == ["a", "b", "start"])
m.sels[KI] = [d for d, _ in K.DOES].index("song")
press("a")
check(f"...a random song ({rows()[2]})", rows()[2] == ("A B START", "Play a random song"))
m.go_home()
plays.clear()
code("a", "b", "start")
check(f"...put in: a song ({plays})", len(plays) == 1 and m.view == "home")
record(done=False)
m.konami_rec["at"] -= K.REC_GIVE_UP + 0.1
m.tick()
check("nothing pressed for a while: not after all", m.konami_rec is None and m.konami_pick is None)
record(done=False)
m.go_home()
m.tick()
check("somewhere else meanwhile: not after all", m.konami_rec is None)
record(*(["up", "down", "left"] + ["right"] * 20), done=False)
check(f"16 buttons at most: done there ({m.konami_pick and len(m.konami_pick['keys'])})",
      m.konami_pick is not None and len(m.konami_pick["keys"]) == K.CODE_MOST)
press("b")
check(f"...B: back, nothing kept ({len(rows())})", m.konami_pick is None and len(rows()) == 4)

# ---- X: what it does, changed; Y twice: forgotten ---------------------------------------------------------------------
on_page()
m.sels[KI] = 1
press("x")
check(f"X: what it does, to pick (on Turn the TV on) ({m.tab_items(KI)[m.sels[KI]]['src']})",
      m.konami_pick is not None and m.tab_items(KI)[m.sels[KI]]["src"] == "tv:on")
press("down", "down", "down", "down")
check(f"...Open: which app, Weather first ({m.tab_items(KI)[m.sels[KI]]['sub']!r}, {m.list_hints()})",
      m.tab_items(KI)[m.sels[KI]]["sub"] == "◀  Weather  ▶" and ("◀▶", "Which app") in m.list_hints())
press("right")
nxt = K.open_names()[K.open_names().index("Weather") + 1]
press("a")
check(f"...◀▶, then A: that app ({rows()[1]})", rows()[1] == ("▲ ▲ ▼ ◀ ▼ ▶ A", f"Open {nxt}"))
press("y")
check(f"Y: press it again ({toasts[-1:]})", toasts[-1] == "Press Y again to forget that code" and len(rows()) == 4)
press("y")
check(f"...again: forgotten ({rows()}, {toasts[-1:]})", len(rows()) == 3 and toasts[-1] == "Forgot ▲ ▲ ▼ ◀ ▼ ▶ A")
m.sels[KI] = 0
press("a")
check(f"A on a code: tried ({progs})", progs[-1:] == ["cmatrix"])
on_page()
m.sels[KI] = 0
press("y", "y", "y", "y")
check(f"the others forgotten too: none ({rows()})", rows() == [("New code", "Press it, then pick what it does")])
m.go_home()
toasts.clear()
check(f"HOME and a button with none: said, no box ({toasts[-1:]})", m.konami_listen() is True and m.view == "home"
      and toasts[-1:] == ["No codes yet: make one in Apps > Konami code"])
m2 = g.Media()
check("...and none it stays (it doesn't come back)", m2.konami_codes() == [])
m2.set_setting("konami", [{"keys": ["up", "down", "a"], "do": "open:Simulator"}])
check(f"a code made when Apps was the Simulator: it opens Apps ({m2.konami_codes()})",
      m2.konami_codes() == [{"keys": ["up", "down", "a"], "do": "open:Apps"}])
out = m.web_command({"cmd": "open", "app": "Simulator"})
check(f"...and the web page asked for the Simulator by its old name: Apps ({out}, {g.LIBRARY[m.tab]['name']})",
      out == {"ok": True} and g.LIBRARY[m.tab]["name"] == "Apps" and m.view == "list")
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
