"""Notes, in Apps: what you type on a keyboard, kept as you type (a moment after your last key, and as you leave), a file
a note in Documents/Notes. While its page is up a keyboard types into it (its keys aren't buttons): letters, Enter a
new line, Backspace the last one gone, Esc back to the list. Nothing typed yet: it says to type, or to plug a keyboard
in. The d-pad picks its colours (up and down its words', left and right the background's), A its font (a dozen, each
drawn, Pixel's in its own sizes), Y an effect, each kept and said; X reads it out loud in your Bot's voice (X again stops); L and R go through your notes, R
past the last starting a new one (kept once something's in it). The note you had last opens next time."""
import json, os, shutil, subprocess, sys
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_notes"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Pictures", "Videos", "Documents"):
    os.makedirs(f"{HOME}/{d}")
NOTES = HOME + "/Documents/Notes"
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media()
m.enter()
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
apps = next(t for t in g.LIBRARY if t["name"] == "Apps")
check(f"Apps has Notes, after the Clock ({apps['children'][:3]})", apps["children"][:2] == ["Clock", "Notes"])
ni = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Notes")


def tick(n=1):
    for _ in range(n):
        m.tick()
    m.dirty = True
    m.flush()


def typed(text):
    """Keys on the keyboard (the KeyReader's thread calls notes_key): a letter each, Enter for a new line."""
    for ch in text:
        if ch == "\n":
            m.notes_key("done")
        else:
            m.notes_key("char", ch)
    tick()


said_keys = []
m.keyreader.start = lambda: said_keys.append(("start", m.keyreader.on_key))
m.keyreader.stop = lambda: said_keys.append(("stop", None))
m.open_app(ni)
tick()
s = m.sims["notes"]
plain = FB.last.convert("RGB").tobytes()
check(f"opened: a new note, empty; the keyboard types into it now ({s.which}, {said_keys[-1:]})",
      s.text == "" and s.which == (1, 1) and m.note_path is None and said_keys[-1] == ("start", m.notes_key)
      and m.notes_typing())
check("...nothing typed: it says to plug in a keyboard (none here)", not s.keyboard)


class Kb:
    mouse = False


m.pads = type("Pads", (), {"keyboards": {"/dev/input/event9": Kb()}})()
tick()
check(f"...a keyboard connects: the keyboard read again, with it too, and the page says to type ({said_keys[-1:]})",
      s.keyboard and said_keys[-1] == ("start", m.notes_key))

typed("Shopping\n- eggs\n- milkk")
m.notes_key("back")
tick()
check(f"typed: letters, Enter a new line, Backspace the last one gone ({s.text!r})", s.text == "Shopping\n- eggs\n- milk")
check("...drawn on its page", FB.last.convert("RGB").tobytes() != plain)
check("...not kept yet, the moment you're typing", not os.path.exists(NOTES))
m.note_changed -= 2                                   # (a moment later)
tick()
note1 = NOTES + "/Note 1.txt"
check(f"...a moment after the last key: kept, as Note 1 ({os.listdir(NOTES) if os.path.isdir(NOTES) else None})",
      os.path.isfile(note1) and open(note1).read() == "Shopping\n- eggs\n- milk" and m.note_path == note1
      and s.which == (1, 1))

for name, key, want in (("up", "ink", "Ink"), ("down", "ink", "White"), ("down", "ink", "Amber"),
                        ("right", "paper", "Black"), ("left", "paper", "Night"), ("left", "paper", "Paper"),
                        ("a", "font", "Handwriting"), ("a", "font", "Typewriter"), ("y", "effect", "Glow"),
                        ("y", "effect", "Rainbow")):
    m.press(name)
    tick()
    if s.values.get(key) != want or m.setting(f"sim_notes_{key}") != want:
        break
check(f"the d-pad its colours, A its font, Y its effect: each kept, and said ({toasts[-1:]}, {s.values})",
      s.values == {"ink": "Amber", "paper": "Paper", "font": "Typewriter", "size": "Normal", "effect": "Rainbow"}
      and m.setting("sim_notes_paper") == "Paper" and toasts[-1] == "Effect: Rainbow")
check(f"...its page in them (the background: the paper's) ({FB.last.getpixel((320, 300))})",
      FB.last.convert("RGB").getpixel((320, 300)) == (246, 240, 226))

pics, fonts = set(), []
for k in range(len(g.NOTE_FONTS)):                    # (A, once round: every font, each drawn its own way)
    m.press("a")
    tick()
    fonts.append(s.values["font"])
    pics.add(FB.last.convert("RGB").tobytes())
check(f"...A all the way round: every font, each its own, and back to the one it was on ({fonts})",
      fonts[-1] == "Typewriter" and sorted(fonts) == sorted(g.NOTE_FONTS) and len(pics) == len(g.NOTE_FONTS)
      and all(os.path.isfile(g.typeface(f)[0]) for f in g.NOTE_FONTS))
sizes = []
for font in ("Clean", "Pixel"):
    for size in ("Small", "Normal", "Big"):
        s.configure({"font": font, "size": size})
        sizes.append(s.font_size()[1])
check(f"...Size (START's card): Small, Normal, Big; Pixel's in steps of 4, never below 12 ({sizes})",
      sizes[0] < sizes[1] < sizes[2] and sizes[3:] == [12, 16, 24])
s.configure({"font": "Typewriter", "size": "Normal"})
aloud = []
m.say_aloud = lambda text=None: (aloud.append(text), (True, ""))[1]
stopped = []
m.voice.stop = lambda *a, **k: stopped.append(1)
m.press("x")
m.voice.speaking = True
tick()
check(f"X: read out loud, in your Bot's voice; its button says Stop while it is ({aloud}, {s.hints()[-1]})",
      aloud == ["Shopping\n- eggs\n- milk"] and s.hints()[-1] == ("X", "Stop"))
m.press("x")
m.voice.speaking = False
tick()
check(f"...X again: stopped ({stopped})", stopped == [1] and s.hints()[-1] == ("X", "Read it"))

m.press("r")
tick()
check(f"R: the note after it, past the last a new one, empty ({s.which}, {s.text!r})",
      s.which == (2, 2) and s.text == "" and m.note_path is None)
m.press("l")
tick()
check(f"...L straight back: an empty new note isn't kept ({sorted(os.listdir(NOTES))}, {s.text!r})",
      sorted(os.listdir(NOTES)) == ["Note 1.txt"] and s.text.startswith("Shopping") and s.which == (1, 1))
m.press("r")
typed("Ideas")
m.press("l")
tick()
check(f"...one with something in it: kept as you go to another (Note 2), and L back to the first ({s.which})",
      open(NOTES + "/Note 2.txt").read() == "Ideas" and s.which == (1, 2) and s.text.startswith("Shopping"))
m.press("l")
tick()
check(f"...L on the first: says so ({toasts[-1:]})", toasts[-1] == "That's your first note" and s.which == (1, 2))
m.press("r")
tick()
check(f"...R: Note 2 again ({s.which}, {s.text!r})", s.which == (2, 2) and s.text == "Ideas")

typed(" for later")
m.notes_key("cancel")                                 # (Esc on the keyboard)
tick()
check(f"Esc: back to the list, as B; what you typed kept at once, and the keyboard let go ({m.view}, "
      f"{said_keys[-1:]})", not m.notes_shown() and open(NOTES + "/Note 2.txt").read() == "Ideas for later"
      and said_keys[-1] == ("stop", None) and not m.notes_typing())
m.open_app(ni)
tick()
check(f"opened again: the note you had last ({s.which}, {s.text!r})", s.which == (2, 2) and s.text == "Ideas for later")
typed("!")
m.leave()
check("...media mode left with it up (the terminal, the Pi shutting down): what you typed kept",
      open(NOTES + "/Note 2.txt").read() == "Ideas for later!")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
