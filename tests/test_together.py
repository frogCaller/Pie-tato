"""Two players on two of your Pietatos (screens/together.py): this one (the handheld, "gpi") and another in a process
of its own (the TV's, "tv": peer_pietato.py), each with its web page. A game two can play (NES): its menu has Play
together, the TV's name beside it (only while it's on; a Game Boy Advance game hasn't). A: the TV's asked; this game's
opened to it (only from the TV's address, with a key) and the TV shows who's asking, and what: A to play, B for no
thanks (not answered in a minute: no thanks). A there: the TV's game joins this one, as player 2 (its saves apart:
yours there never change), and this one's told; then the menus leave out what'd put the two out of step, and say
who's playing. The TV leaving: this one plays on; this one ending it: the TV's ends too, and says so. A game the TV
hasn't got: copied over first. A Game Boy game: Link cable, A twice (it starts from the game's own save); this game
again, linked (gambatte, the end the other joins), and the TV picks which of its Game Boy games (◀▶), linked to this
one's address; each one's save back with its own after, where you were in it put aside if it changed (it'd take a
trade back), and kept if nothing changed. Not from one that isn't one of yours; the web page's part, your network
only."""
import json, os, shutil, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.screens.together as T

S = SP + "/t_together"
shutil.rmtree(S, ignore_errors=True)
HOME, TV = S + "/gpi", S + "/tv"
for h in (HOME, TV):
    for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves", "Games/nes", "Games/gb", "Games/gba"):
        os.makedirs(f"{h}/{d}")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- the helpers, on their own -------------------------------------------------------------------------------------
check("a link cable's address, as gambatte takes it: 12 digits, 3 for each part (not one like fe80::1)",
      T.link_options(False, "192.168.1.20")[2:] == [f"gambatte_gb_link_network_server_ip_{i + 1}={d}"
                                                     for i, d in enumerate("192168001020")]
      and T.link_options(True)[:1] == ["gambatte_gb_link_mode=Network Server"]
      and T.link_options(False, "fe80::1") is None and T.link_options(False, "nope") is None)
check("a save back from the link cable: what another emulator kept after it, kept",
      T.keep_tail(b"new", b"oldCLOCK") == b"newCLOCK" and T.keep_tail(b"newer", b"ol") == b"newer"
      and T.keep_tail(b"x", None) == b"x")

# ---- this one: the handheld ------------------------------------------------------------------------------------------
CONTRA = "Contra (USA)"
ROM = HOME + "/Games/nes/" + CONTRA + ".nes"
open(ROM, "wb").write(bytes(range(256)) * 96)
RED = HOME + "/Games/gb/Pokemon Red (USA).gb"
open(RED, "wb").write(b"\x01" * 4096)
GBA = HOME + "/Games/gba/Golden Sun (USA).gba"
open(GBA, "wb").write(b"\x02" * 4096)
SRAM = b"S" * 32 + b"mGBA-clock"                       # (mGBA's: the game's save, then its clock)
REDSAVE = HOME + "/Games/Saves/Pokemon Red (USA)"
os.environ["HOME"] = HOME
g.STATE_FILE = S + "/gpi.json"; g.CACHE_DIR = S + "/gpicache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: ""
g.built_for_other_pi = lambda core: False
T.link_core = lambda: "/fake/gambatte_libretro.so"
starts, sent, asked, told = [], [], [], []


def game_start(self, core, **kw):
    self.state = "on"
    self.kw = kw
    starts.append((self.game["path"], core, kw))


def game_quit(self, timeout=0):
    if getattr(self, "quitted", False):
        return
    self.quitted = True
    if not self.kw.get("saves"):                       # (yours, written as the emulator writes them; a game played
        base = os.path.join(g.games_dir(), g.SAVES_FOLDER, g.save_name(self.game["path"]))   # together: the test's)
        open(base + ".srm", "wb").write(SRAM)
        open(base + ".state.auto", "w").write("where you were")
    self.ended = True


def game_ask(self, line, wants, timeout=3.0):
    asked.append(line)
    return ("nethost", "ok 5442") if line.startswith("nethost ") else (None, "")


g.GameRun.start = game_start
g.GameRun.quit = game_quit
g.GameRun.ask = game_ask
g.GameRun.send = lambda self, line: sent.append(line) or True
g.GameRun.pause = lambda self: True
g.GameRun.resume = lambda self: None


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img
    def show_part(self, img, box): pass
    def invalidate(self): pass
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
m.saves_tell = lambda run: told.append(run.game["path"])
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = HOME
webui.STATIC = S + "/gpistatic"
os.makedirs(webui.STATIC + "/fonts")
webui.STATE_FILE = g.STATE_FILE
webui.CONTROL = ("127.0.0.1", server.server_address[1])
webui.CONTROL_KEY = S + "/control-key"
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
from werkzeug.serving import make_server
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
MINE = f"http://127.0.0.1:{web.server_port}"


def pump(until, secs=8.0):
    """This one's main loop, a while: what the TV's web page asked of it, done (till until() is true)."""
    end = time.time() + secs
    while True:
        for job in control.take():
            m.stir()
            try:
                out = m.web_command(job["cmd"])
            except Exception as ex:
                out = {"error": repr(ex)}
            control.done(job, out)
        if until() or time.time() > end:
            return until()
        time.sleep(0.05)


# ---- the other one: the TV's --------------------------------------------------------------------------------------------
LOG = S + "/tv.log"
open(LOG, "w").close()
shutil.copy(ROM, TV + "/Games/nes/" + CONTRA + ".nes")    # (it has the same game)
for name in ("Pokemon Blue (USA)", "Pokemon Yellow (USA)"):
    open(f"{TV}/Games/gb/{name}.gb", "wb").write(b"\x03" * 4096)
BLUESAVE = TV + "/Games/Saves/Pokemon Blue (USA)"
open(BLUESAVE + ".srm", "w").write("tv's blue save")
open(BLUESAVE + ".state.auto", "w").write("where the tv was")
tv = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", TV, LOG, "tv", MINE, "gpi"],
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
line = tv.stdout.readline().split()
if line[:1] != ["READY"]:
    print("FAIL the TV's Pietato didn't start", line)
    sys.exit(1)
THEIRS = line[1]


def tv_said(key, since=0, secs=8.0):
    end = time.time() + secs
    while True:
        rows = [json.loads(x) for x in open(LOG).read().splitlines()[since:] if x.strip()]
        hits = [r for r in rows if key in r]
        if hits or time.time() > end:
            return hits[-1] if hits else None
        time.sleep(0.1)


def tv_lines():
    return len(open(LOG).read().splitlines())


def tv_do(line):
    tv.stdin.write(line + "\n")
    tv.stdin.flush()
    return tv.stdout.readline().strip()


def tv_state():
    return json.loads(tv_do("state"))


def tv_until(cond, secs=8.0):
    end = time.time() + secs
    while True:
        st = tv_state()
        if cond(st) or time.time() > end:
            return st
        time.sleep(0.1)


def opened(path, system):
    m.game_open({"src": path, "title": g.game_title(path), "system": system})
    m.game_menu_open()


def jobs():
    return [k for k, _ in m.game_menu_items()]


def ident_of(path, system):
    return dict(T.game_ident(path, g.games_dir(), system, g.game_title(path), g.save_name(path)))


try:
    # ---- a game's menu -------------------------------------------------------------------------------------------
    opened(ROM, "nes")
    check(f"no other Pietato on: no Play together ({jobs()})", "together" not in jobs())
    m.pie.heard[THEIRS] = {"host": "tv", "seen": time.time() + 3600, "peer": True}
    rows = dict(m.game_menu_items())
    check(f"the TV's on: Play together, with its name, before Play on another Pietato ({jobs()[-3:]}, "
          f"{m.game_value('together')})", jobs()[-3:] == ["together", "send", "quit"]
          and rows["together"] == "Play together" and m.game_value("together") == "tv")
    m.game_end()
    opened(GBA, "gba")
    check(f"...a Game Boy Advance game: not (no link cable here for it) ({jobs()})", "together" not in jobs())
    m.game_end()

    # ---- asked: the TV says no thanks ---------------------------------------------------------------------------------------
    opened(ROM, "nes")
    m.game_do("together")
    run = m.game
    key = asked[-1].split()[2] if asked and asked[-1].startswith("nethost ") else ""
    check(f"A: this game's opened to the TV, its address only, with a key ({asked[-1:]})",
          asked[-1:] == [f"nethost 5442 {key} 127.0.0.1"] and len(key) >= 20)
    check(f"...back in the game, saying the TV's asked ({m.view}, {sent[-1:]})", m.view == "game"
          and sent[-1:] == ["notice Asking tv to play"] and run.together["state"] == "asked")
    st = tv_state()
    check(f"the TV: who's asking, and what (A or B) ({st['view']}, {st['invite']})", st["view"] == "invite"
          and st["invite"]["host"] == "gpi" and st["invite"]["title"] == g.game_title(ROM)
          and st["invite"]["link"] is False)
    tv_do("press b")
    answered = pump(lambda: "notice tv said no thanks" in sent)
    check(f"B there: no thanks, said here, the game no longer open to it ({sent[-2:]})",
          answered and sent[-1] == "netstop" and run.together is None)
    check(f"...and the TV's back where it was ({tv_state()['view']})", tv_state()["view"] == "home")

    # ---- asked, not answered in time -----------------------------------------------------------------------------------
    sent.clear()
    m.game_do("together")
    tv_until(lambda st: st["view"] == "invite")
    tv_do("expire")
    answered = pump(lambda: "notice tv said no thanks" in sent)
    check(f"not answered in a minute: no thanks ({sent[-2:]})", answered and run.together is None
          and tv_until(lambda st: st["view"] == "home")["view"] == "home")

    # ---- yes: the TV joins, as player 2 ------------------------------------------------------------------------------------
    sent.clear()
    n = tv_lines()
    m.game_do("together")
    key = asked[-1].split()[2]
    tv_until(lambda st: st["view"] == "invite")
    tv_do("press a")
    started = tv_said("started", n)
    check(f"A there: the TV's own copy joins this game, with the key ({started and started['net']})",
          started is not None and started["started"] == TV + "/Games/nes/" + CONTRA + ".nes"
          and started["net"] == f"127.0.0.1:5442:{key}")
    check(f"...its saves apart from the TV's own, from this game as it is (not its own place in it), no achievements "
          f"({started and started['saves']}, {started and started['resume']}, {started and started['cheevos']})",
          started is not None and started["saves"] == TV + "/.pietato/cache/together/Saves"
          and started["resume"] is False and started["cheevos"] is False)
    answered = pump(lambda: "notice tv said yes" in sent)
    check(f"...and this one's told ({sent[-1:]})", answered and run.together["state"] == "coming")
    run.net_news.append(("netjoined", "tv"))
    m.game_tick(time.monotonic())
    m.game_menu_open()
    check(f"joined: this one's menu says so, and leaves out what'd put the two out of step ({jobs()}, "
          f"{m.together_note()})", run.together["state"] == "on" and m.together_note() == "Playing with tv (player 2)"
          and not {"load", "reset", "ai", "send", "together"} & set(jobs()) and {"save", "quit"} <= set(jobs()))
    st = tv_state()
    check(f"...the TV's too: no saving there (it's this one's game) ({st['menu']}, {st['note']})",
          not {"save", "load", "reset", "ai", "send", "together"} & set(st["menu"]) and "quit" in st["menu"]
          and st["note"] == "Playing gpi's game: you're player 2")
    out = T.together_post(THEIRS, dict(ident_of(ROM, "nes"), kind="ask"), 4)
    check(f"...and while it plays, it can't be asked again ({out})", out == {"ok": False,
                                                                           "error": "It's playing a game"})
    m.game_menu_close()

    # ---- the TV leaves; this one ends it ---------------------------------------------------------------------------------
    toasts.clear()
    run.net_news.append(("netleft", "it left"))
    m.game_tick(time.monotonic())
    check(f"the TV leaves: this one plays on, alone, and says so ({toasts[-1:]})", toasts[-1:] == ["tv left"]
          and run.together is None and m.game is run and "together" in jobs())
    n = tv_lines()
    tv_do("news netgone it left")
    said = tv_said("toast", n)
    check(f"this one ending it: the TV's game ends, and says why ({said})", said == {"toast": "gpi ended the game"}
          and tv_until(lambda st: st["game"] is None)["game"] is None)
    check("...the TV's own saves never changed (player 2's were apart)",
          not os.path.exists(TV + "/Games/Saves/" + CONTRA + ".srm")
          and os.path.exists(TV + "/.pietato/cache/together/Saves/" + CONTRA + ".srm"))

    # ---- a game the TV hasn't got: copied over first ----------------------------------------------------------------------
    os.remove(TV + "/Games/nes/" + CONTRA + ".nes")
    n = tv_lines()
    m.game_do("together")
    tv_until(lambda st: st["view"] == "invite")
    tv_do("press a")
    started = tv_said("started", n, secs=15)
    copied = TV + "/Games/nes/" + CONTRA + ".nes"
    check(f"a game the TV hasn't got: copied over (the same game), then it joins ({started and started['started']})",
          started is not None and started["started"] == copied and open(copied, "rb").read() == open(ROM, "rb").read()
          and not [x for x in os.listdir(TV + "/Games/nes") if x.endswith(".part")])
    tv_do("news netgone it stopped answering")
    pump(lambda: run.together is not None and run.together["state"] == "coming", 3)
    m.game_end()
    check(f"...this one's game, ended: its saves yours, your other Pietatos told ({told[-1:]})",
          told[-1:] == [ROM] and open(HOME + "/Games/Saves/" + CONTRA + ".srm", "rb").read() == SRAM)

    # ---- a Game Boy game: a link cable ----------------------------------------------------------------------------------
    opened(RED, "gb")
    rows = dict(m.game_menu_items())
    check(f"a Game Boy game: Link cable ({rows.get('together')})", rows.get("together") == "Link cable")
    m.game_menu["sel"] = jobs().index("together")
    toasts.clear()
    m.press("a")
    check(f"A once: it says it starts from the game's own save, A again to link up ({toasts[-1:]}, "
          f"{m.game_menu and m.game_menu['confirm'][0]})", toasts[-1:] == [
              "The link cable starts from the game's own save, the last time you saved in it"]
          and m.game_menu is not None and m.game_menu["confirm"][0] == "together" and starts[-1][1].endswith("gb_libretro.so"))
    sent.clear()
    m.press("a")
    path, core, kw = starts[-1]
    LINK = g.CACHE_DIR + "/link/Saves"
    check(f"A again: the game again, linked: gambatte, the end the TV joins ({os.path.basename(core)}, "
          f"{kw.get('options')})", path == RED and core == "/fake/gambatte_libretro.so"
          and kw.get("options") == ["gambatte_gb_link_mode=Network Server", "gambatte_gb_link_network_port=56400"])
    check(f"...from the game's own save, a copy of it ({kw.get('saves')}, {kw.get('resume')})",
          kw.get("saves") == LINK and kw.get("resume") is False and kw.get("cheevos") is False
          and open(LINK + "/Pokemon Red (USA).srm", "rb").read() == SRAM)
    st = tv_state()
    check(f"the TV: who's asking, and which of its Game Boy games ({st['invite']})", st["view"] == "invite"
          and st["invite"]["link"] is True and st["invite"]["title"] == g.game_title(RED)
          and st["invite"]["games"] == ["Pokemon Blue (USA)", "Pokemon Yellow (USA)"] and st["invite"]["pick"] == 0)
    tv_do("press right")
    picked = tv_state()["invite"]["pick"]
    tv_do("press left")
    n = tv_lines()
    tv_do("press a")
    started = tv_said("started", n)
    check(f"...◀▶ picks one ({picked}), A: it's linked to this one's address "
          f"({started and started['options'][:2]}, {started and ''.join(o[-1] for o in started['options'][2:])})",
          picked == 1 and started is not None and started["started"] == TV + "/Games/gb/Pokemon Blue (USA).gb"
          and started["core"] == "/fake/gambatte_libretro.so"
          and started["options"] == T.link_options(False, "127.0.0.1"))
    check("...from a copy of its own save", started is not None and started["saves"] == TV + "/.pietato/cache/link/Saves"
          and open(TV + "/.pietato/cache/link/Saves/Pokemon Blue (USA).srm").read() == "tv's blue save")
    answered = pump(lambda: "notice tv is linking up" in sent)
    check(f"...and this one's told ({sent[-1:]})", answered)
    m.game_menu_open()
    check(f"linked: the menu says so, no saving or loading states (the game's own save's the one) ({jobs()}, "
          f"{m.together_note()})", m.together_note() == "Link cable with tv"
          and not {"save", "load", "reset", "ai", "send", "together"} & set(jobs()))
    m.game_menu_close()
    g.GameRun.pause = lambda self: False               # (it doesn't answer: standing still, the TV's not at the link)
    m.game_menu_open()
    check(f"...standing still, waiting for the TV's game at the link: its menu all the same, saying so ({m.view}, "
          f"{m.together_note()})", m.view == "gamemenu" and m.together_note() == "The link cable's waiting for tv")
    g.GameRun.pause = lambda self: True
    open(LINK + "/Pokemon Red (USA).srm", "wb").write(b"T" * 32)   # (a Pokemon traded, the game saved)
    told.clear()
    m.game_do("quit")
    check(f"the game ended: its save back with yours, mGBA's clock after it kept ({open(REDSAVE + '.srm', 'rb').read()})",
          open(REDSAVE + ".srm", "rb").read() == b"T" * 32 + b"mGBA-clock" and told == [RED])
    check("...where you were in it, put aside (it'd take the trade back): next time it starts from that save",
          not os.path.exists(REDSAVE + ".state.auto")
          and open(HOME + "/Games/Saves/.replaced/Pokemon Red (USA).state.auto").read() == "where you were")
    tv_do("news netgone it left")
    end = time.time() + 8
    while os.path.exists(BLUESAVE + ".state.auto") and time.time() < end:   # (its game ending, there)
        time.sleep(0.1)
    check("the TV's too, its own (and where it was, put aside)",
          open(BLUESAVE + ".srm").read().startswith("tv's .srm") and not os.path.exists(BLUESAVE + ".state.auto")
          and open(TV + "/Games/Saves/.replaced/Pokemon Blue (USA).state.auto").read() == "where the tv was")

    # ---- linked, and nothing changed: where you were, kept --------------------------------------------------------------
    opened(RED, "gb")
    m.game_menu["sel"] = jobs().index("together")
    m.press("a")
    m.press("a")
    tv_until(lambda st: st["view"] == "invite")
    sent.clear()
    tv_do("press b")
    answered = pump(lambda: "notice tv said no thanks" in sent)
    check(f"the TV says no thanks: the game plays on here, linked (its save back after) ({sent[-1:]})",
          answered and m.together_of() is not None and "netstop" not in sent)
    m.game_end()
    check("...nothing changed: your save as it was, and where you were, kept",
          open(REDSAVE + ".srm", "rb").read() == SRAM and open(REDSAVE + ".state.auto").read() == "where you were")

    # ---- the invitation's card ----------------------------------------------------------------------------------------
    blue = g.find_games()[0]
    m.invite = {"host": "tv", "url": THEIRS, "ident": ident_of(RED, "gb"), "link": True, "port": 56400, "key": "",
                "file": "", "mine": None, "games": [blue, blue], "pick": 0, "from": "home",
                "until": time.monotonic() + 42.5, "shown": None}
    m.view = "invite"
    FB.last = None
    m.render_invite()
    card = FB.last
    if card is not None:
        card.save(S + "/invite.png")
    check(f"its card: drawn (the time left on it: {m.invite['shown']} s)", card is not None and card.size == (640, 480)
          and m.invite["shown"] == 42)
    m.view = "home"
    m.invite_tick(time.monotonic())
    check("...something else on the screen: no thanks", m.invite is None and m.view == "home")

    # ---- not one of yours ----------------------------------------------------------------------------------------------
    out = m.web_together(dict(ident_of(ROM, "nes"), kind="ask", **{"from": "192.168.1.99"}))
    check(f"from a Pi that isn't one of your Pietatos: no ({out})", out == {"ok": False,
                                                                          "error": "Not one of your Pietatos"})
    c = webui.app.test_client()
    far = c.post("/api/together", json={"kind": "ask"}, base_url="http://192.168.1.30:5432",
                 environ_base={"REMOTE_ADDR": "8.8.8.8"})
    near = c.post("/api/together", json={"kind": "play"}, base_url="http://192.168.1.30:5432",
                  environ_base={"REMOTE_ADDR": "192.168.1.31"})
    check(f"...and the web page's part answers your network only, and only what it knows ({far.status_code}, "
          f"{near.status_code})", far.status_code == 403 and near.status_code == 400)
finally:
    try:
        tv.stdin.write("quit\n")
        tv.stdin.flush()
        tv.wait(10)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        tv.kill()
    web.shutdown()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
