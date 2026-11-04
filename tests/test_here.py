"""Play here, on the Pi's side: in a web page's request with it on, what would play on the Pi is handed to the page
instead, if a browser can play it (a video or a song of yours with the rest of its kind, a cartoon from archive.org, a
station; a game EmulatorJS plays, with where its save is), and played on the Pi as ever, with why, if not (Plex, a live
channel, an .avi, a Dreamcast game, a game in more than one file, a file outside your home folder); with it off, or
outside a web page's request, nothing changes."""
import json, os, shutil, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_here"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Videos", "Music/Album", "Games/gb", "Games/ps1", "Games/dc", "Games/BIOS", ".hidden"):
    os.makedirs(f"{HOME}/{d}")
for f in ("Videos/a.mp4", "Videos/b.avi", "Videos/c.mkv", "Music/Album/1.mp3", "Music/Album/2.flac", "Music/Album/3.wma",
          "Games/gb/Zelda.gb", "Games/ps1/Disc.chd", "Games/ps1/Two.cue", "Games/dc/Game.gdi", "Games/BIOS/scph1001.bin",
          ".hidden/x.mp4"):
    open(f"{HOME}/{f}", "wb").write(b"\0" * 64)
os.makedirs(S + "/outside")
open(S + "/outside/o.mp4", "wb").write(b"\0")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"
g.home_dir = lambda: HOME
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


m = g.Media()
played = []
m.spawn = lambda args, target: played.append(target)


def ask(fn, *a):
    """As a web page's request with Play here on: (what's handed over, the answer)."""
    m.here_begin(True)
    took = fn(*a)
    return took, m.here_end({"ok": True})


def it(path, kind, **kw):
    return g.item(path, os.path.basename(path), kind, path, **kw)


vids = [it(f"{HOME}/Videos/{n}", "video") for n in ("a.mp4", "b.avi", "c.mkv")]
m.state["pos"][vids[0]["key"]] = 95.0
took, out = ask(m.here_take, vids, 0)
p = out.get("play", {})
check(f"a video of yours: handed over, with the others a browser plays ({p})", took and p["kind"] == "video"
      and [r["url"] for r in p["items"]] == ["/api/home/Videos/a.mp4", "/api/home/Videos/c.mkv"] and p["index"] == 0
      and p["start"] == 95.0)
took, out = ask(m.here_take, vids, 1)
check(f"an .avi: not handed over, and why ({out})", not took and "play" not in out and "browser can't" in out["note"])
songs = [it(f"{HOME}/Music/Album/{n}", "audio", sub="Someone") for n in ("1.mp3", "2.flac", "3.wma")]
took, out = ask(m.here_take, songs, 1)
p = out.get("play", {})
check(f"a song: it, and its album with it ({[r['title'] for r in p.get('items', [])]}, {p.get('index')})",
      took and p["kind"] == "audio" and len(p["items"]) == 2 and p["index"] == 1 and p["items"][1]["sub"] == "Someone")
toon = g.item("ia:popeye-1936/Popeye The Sailor.mp4", "Popeye", "video", "ia:popeye-1936/Popeye The Sailor.mp4")
took, out = ask(m.here_take, [toon], 0)
check(f"a cartoon: from archive.org ({out['play']['items'][0]['url']})", took and out["play"]["items"][0]["url"]
      == "https://archive.org/download/popeye-1936/Popeye%20The%20Sailor.mp4")
radio = g.item("url:http://radio.example/jazz", "Jazz", "radio", "http://radio.example/jazz")
took, out = ask(m.here_take, [radio], 0)
check(f"a station: its stream ({out['play']})", took and out["play"]["kind"] == "radio"
      and out["play"]["items"][0]["url"] == "http://radio.example/jazz")
for what, row, word in (("Plex", g.item("plex:1", "A film", "plexvideo", "plex:1"), "Plex"),
                        ("a live channel", g.item("plexlive:9", "News", "live", "plexlive:9"), "Live"),
                        ("a file outside your home folder", it(S + "/outside/o.mp4", "video"), "That one plays on the Pi"),
                        ("one in a hidden folder", it(f"{HOME}/.hidden/x.mp4", "video"), "That one plays on the Pi")):
    took, out = ask(m.here_take, [row], 0)
    check(f"{what}: plays on the Pi, and says so ({out})", not took and word in out.get("note", ""))
check("...nothing played meanwhile", played == [])
m.here_begin(False)
took = m.here_take(vids, 0)
m.here_end({"ok": True})
check("Play here off: nothing handed over", not took)
check("...nor outside a web page's request", not m.here_take(vids, 0) and m.web_here is False)

game = dict(it(f"{HOME}/Games/gb/Zelda.gb", "game"), system="gb")
took, out = ask(m.here_take_game, game)
check(f"a Game Boy game: EmulatorJS's core, the game, where its save is ({out.get('play')})", took and out["play"] == {
    "kind": "game", "title": "Zelda.gb", "core": "gambatte", "rom": "Games/gb/Zelda.gb", "bios": "",
    "save": "Saves/Zelda.srm"})
ps1 = dict(it(f"{HOME}/Games/ps1/Disc.chd", "game"), system="ps1")
took, out = ask(m.here_take_game, ps1)
check(f"a PlayStation game: with its BIOS from Games/BIOS ({out['play']['bios']})", took
      and out["play"]["core"] == "pcsx_rearmed" and out["play"]["bios"] == "Games/BIOS/scph1001.bin")
cue = dict(it(f"{HOME}/Games/ps1/Two.cue", "game"), system="ps1")
took, out = ask(m.here_take_game, cue)
check(f"one in more than one file: on the Pi ({out})", not took and "more than one file" in out["note"])
dc = dict(it(f"{HOME}/Games/dc/Game.gdi", "game"), system="dc")
took, out = ask(m.here_take_game, dc)
check(f"a Dreamcast game: on the Pi ({out})", not took and "plays on the Pi" in out["note"])
check("an error's answer stays as it was", m.here_end({"error": "x"}) == {"error": "x"})
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
