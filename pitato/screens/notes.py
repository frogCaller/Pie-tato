"""Notes, in Apps (pitato/notes.py draws it): your notes, a file each in your Documents' Notes folder ("Note 1.txt"...),
kept a moment after you stop typing (and as you leave). While its page is on the screen a keyboard types into it
(inputs.py's KeyReader has the keyboard then: its keys aren't buttons). The d-pad, A (its font) and Y change how it
looks (kept, as START's card keeps them), X reads it out loud in your Bot's voice, L and R go through your notes."""
import os
import re
import time

from ..library import LIBRARY
from ..notes import NOTE_MOST
from ..util import home_folder

NOTES_FOLDER = "Notes"            # in your Documents
NOTES_SAVE = 1.0                  # seconds after the last key before what you typed is kept
NOTES_KEYS = {"up": "ink", "down": "ink", "left": "paper", "right": "paper", "a": "font", "y": "effect"}


def note_number(name):
    """Note 12.txt's 12 (None: a note named otherwise)."""
    m = re.fullmatch(r"Note (\d{1,6})\.txt", name)
    return int(m.group(1)) if m else None


class NotesScreen:
    """Notes: its files, the keyboard while it's up, and its buttons."""

    def notes_shown(self):
        """The Notes page is on the screen (its START card shut): a keyboard types into it."""
        return bool(self.active and self.view == "list" and self.tab_type() == "sim"
                    and LIBRARY[self.tab].get("sim") == "notes" and self.sim_opts is None)

    def notes_folder(self):
        return os.path.join(home_folder("Documents"), NOTES_FOLDER)

    def notes_files(self):
        """Your notes, in order: Note 1, Note 2... then any others, by name."""
        folder = self.notes_folder()
        try:
            names = [n for n in os.listdir(folder) if n.lower().endswith(".txt") and not n.startswith(".")
                     and os.path.isfile(os.path.join(folder, n))]
        except OSError:
            return []
        names.sort(key=lambda n: (note_number(n) is None, note_number(n) or 0, n.lower()))
        return [os.path.join(folder, n) for n in names]

    def notes_open(self, path):
        """A note on the page: one of your files, or a new one (None: no file till something's typed in it)."""
        s = self.sim_game()
        text = ""
        if path is not None:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read(NOTE_MOST)
            except OSError:
                path = None
        self.note_path, self.note_changed = path, None
        s.text = text
        files = self.notes_files()
        s.which = ((files.index(path) + 1, len(files)) if path in files else (len(files) + 1, len(files) + 1))
        if path is not None:
            self.set_setting("notes_last", os.path.basename(path))
        self.dirty = True

    def notes_start(self):
        """The page just opened: the note you had last (or your newest, or a new one)."""
        files = self.notes_files()
        last = self.setting("notes_last")
        named = [p for p in files if os.path.basename(p) == last]
        self.notes_open(named[0] if named else files[-1] if files else None)

    def notes_save(self):
        """The note on the page, kept, if it's changed: written whole (a new one: named for the next number). A new
        one with nothing in it isn't kept."""
        s = self.sims.get("notes")
        if s is None or getattr(self, "note_changed", None) is None:
            return
        self.note_changed = None
        path = getattr(self, "note_path", None)
        if path is None:
            if not s.text.strip():
                return
            folder = self.notes_folder()
            taken = [note_number(os.path.basename(p)) or 0 for p in self.notes_files()]
            path = os.path.join(folder, f"Note {max(taken, default=0) + 1}.txt")
        try:
            folder = os.path.dirname(path)
            if not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)
                st = os.stat(os.path.dirname(folder))
                os.chown(folder, st.st_uid, st.st_gid)  # (yours, as Documents is)
            st = os.stat(folder)
            tmp = os.path.join(folder, "." + os.path.basename(path) + ".part")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(s.text)
            os.chown(tmp, st.st_uid, st.st_gid)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except OSError as ex:
            print(f"notes: couldn't keep {os.path.basename(path)}: {ex}", flush=True)
            self.toast(f"Couldn't keep the note ({ex.strerror or ex})", 4)
            return
        if path != self.note_path:                     # (a new one, kept: it's one of your notes now)
            self.note_path = path
            self.set_setting("notes_last", os.path.basename(path))
            files = self.notes_files()
            s.which = (files.index(path) + 1 if path in files else len(files), len(files))
            self.dirty = True

    def notes_tick(self, now):
        """Each tick: a keyboard types into the page while it's up (and again as one's plugged in or connects), not
        once it's gone; what you typed kept a moment after your last key; whether there's a keyboard, and whether
        it's being read out loud, as its page says."""
        shown = self.notes_shown()
        kbs = (frozenset(p for p, k in self.pads.keyboards.items() if not k.mouse)
               if shown and getattr(self, "pads", None) is not None else frozenset())
        if shown and (not self.notes_reading or kbs != self.notes_kbs):
            if not self.notes_reading:
                self.notes_start()
            self.notes_reading, self.notes_kbs = True, kbs
            self.keyreader.on_key = self.notes_key
            self.keyreader.start()
        elif not shown and self.notes_reading:
            self.notes_reading = False
            if self.keyreader.on_key == self.notes_key:
                self.keyreader.stop()
            self.notes_save()
        if self.note_changed is not None and now - self.note_changed >= NOTES_SAVE:
            self.notes_save()
        s = self.sims.get("notes")
        if shown and s is not None:
            aloud = self.notes_aloud and bool(self.voice.speaking)
            self.notes_aloud = aloud
            if (s.keyboard, s.reading) != (bool(kbs), aloud):
                s.keyboard, s.reading = bool(kbs), aloud
                self.dirty = True

    def notes_typing(self):
        """A keyboard's keys are the note's now (not buttons)."""
        return self.notes_shown()

    def notes_key(self, kind, ch=""):
        """A key on the keyboard (from the KeyReader's own thread): typed into the note, on media mode's."""
        self.soon(lambda: self.notes_typed(kind, ch))
        self.wake()

    def notes_typed(self, kind, ch=""):
        """A letter (or a space...) typed, Backspace the last one gone, Enter a new line; Esc goes back, as B does."""
        s = self.sims.get("notes")
        if s is None or not self.notes_shown():
            return
        if kind == "cancel":
            self.press("b")
            return
        if kind == "char":
            s.text = (s.text + ch)[:NOTE_MOST]
        elif kind == "back":
            s.text = s.text[:-1]
        elif kind == "done":
            s.text = (s.text + "\n")[:NOTE_MOST]
        else:
            return
        self.note_changed = time.monotonic()
        self.stir()
        self.dirty = True

    def press_notes(self, s, name, repeat):
        """Its buttons: up and down the words' colour, left and right the background's, A the font, Y the effect
        (each kept, as START's card keeps it, and said), X reads it out loud (X again stops), L and R the note before
        or after (R past the last: a new one). B: back to the list ("pass"). False: as for any of Apps' (SELECT,
        START)."""
        if name == "b":
            return "pass"
        if repeat:
            return None if name in NOTES_KEYS or name in ("x", "l", "r") else False
        if name in NOTES_KEYS:
            key = NOTES_KEYS[name]
            label, ways = next((label, list(ways)) for k, label, ways, _ in s.options if k == key)
            cur = s.values.get(key)
            new = ways[((ways.index(cur) if cur in ways else 0) + (-1 if name in ("up", "left") else 1)) % len(ways)]
            self.set_setting(f"sim_notes_{key}", new)
            s.configure({key: new})
            self.toast(f"{label}: {new}", 2)
        elif name == "x":
            self.notes_read(s)
        elif name in ("l", "r"):
            self.notes_step(-1 if name == "l" else 1)
        else:
            return False
        self.dirty = True
        return None

    def notes_read(self, s):
        """X: the note read out loud in your Bot's voice (Settings > Bot), or that stopped."""
        if self.notes_aloud and self.voice.speaking:
            self.voice.stop()
            self.notes_aloud = False
            return
        if not s.text.strip():
            self.toast("There's nothing to read yet", 2)
            return
        ok, why = self.say_aloud(s.text)
        if ok:
            self.notes_aloud = True
        else:
            self.toast(why, 3)

    def notes_step(self, way):
        """L or R: the note before or after this one; R past the last, a new one (empty: kept once there's something
        in it)."""
        self.notes_save()
        files = self.notes_files()
        cur = files.index(self.note_path) if self.note_path in files else len(files)
        new = cur + way
        if new < 0:
            self.toast("That's your first note", 2)
            return
        if new >= len(files):
            if self.note_path is None:
                self.toast("A new note. Type away", 2)
                return
            self.notes_open(None)
            self.toast("A new note", 2)
            return
        self.notes_open(files[new])
