#!/usr/bin/env python3
"""hear.py - the bot's ears: a USB microphone, made sense of by Vosk on the Pi itself.

Pietato (pitato/listen.py) runs this as you rather than as root, as it does Piper: what it reads, a speech model,
comes from the internet. It records with arecord and says what it makes out, a line of JSON at a time:
    {"ready": true, "unknown": [...]}   its model is loaded (and the words of yours it doesn't know)
    {"partial": "..."}                  what's being said, so far
    {"final": "..."}                    something said, at its end
    {"error": "..."}                    it can't go on (and it stops)
It's told, a line at a time: "deaf" (what it hears is let go, unheard: the bot is speaking, say), "listen",
"reset" (what it was making out, forgotten), "noisy" and "clear" (music playing, or not), and "quit". Only Python's
own modules: it runs with -I.

Over music, making out everything that's said hears the wake phrase hardly ever: the song's words and its own get in
the way. So while something plays it listens for the wake phrase alone (a grammar of it and everyday words, a song's
or a talk show's, for what else it hears to go to), and only when Vosk's sure of it; then, once the music's paused or
quieter (a moment), what you say, as ever. With your own words for the wake phrase it doesn't know, it makes out
everything, as ever.

    python3 -I hear.py <libvosk.so> <model folder> <microphone, or ""> [words it should know...]
"""
import ctypes
import json
import os
import select
import subprocess
import sys
import tempfile
import time

RATE = 16000
CHUNK = 4000             # bytes at a time: an eighth of a second
SPOT_SURE = 0.7          # how sure Vosk must be of the wake phrase's words, heard over music (it hears them in songs)
AFTER_SKIP = 0.5         # seconds after the wake phrase (heard over music) let go: the music going quieter
AFTER_MOST = 15.0        # ...and what's said after it is made out for this long, at most
SWAPS = {"hey": "hi", "hi": "hey", "ok": "okay", "okay": "ok"}   # (a greeting heard for its twin)
EVERYDAY = """the a an and or but so of to in on at for with from up down out over off by as is are was were be been am
i you he she it we they me him her us them my your his its our their this that these those what which who how why when
where yes no not oh ah yeah hey baby love night day light time life heart feel know go come get make take see look say tell
want need like just all one two three now here there then again away back home road city summer air right hold let
through every little thing dancing singing along young walking tonight under lights can will would could should do did
done have has had la na da ba ooh whoa uh um mm hmm ya ay well good bad more less some any many much very really still never
always ever only even also too around into about after before while until because if than""".split()


def say(**what):
    try:
        sys.stdout.write(json.dumps(what) + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        raise SystemExit(0)                       # (Pietato's gone: so is this)


def vosk(path):
    """Vosk's library, with what's used of it."""
    lib = ctypes.CDLL(path)
    c = ctypes
    for name, args, res in (("vosk_set_log_level", [c.c_int], None),
                            ("vosk_model_new", [c.c_char_p], c.c_void_p),
                            ("vosk_model_free", [c.c_void_p], None),
                            ("vosk_model_find_word", [c.c_void_p, c.c_char_p], c.c_int),
                            ("vosk_recognizer_new", [c.c_void_p, c.c_float], c.c_void_p),
                            ("vosk_recognizer_new_grm", [c.c_void_p, c.c_float, c.c_char_p], c.c_void_p),
                            ("vosk_recognizer_set_words", [c.c_void_p, c.c_int], None),
                            ("vosk_recognizer_set_partial_words", [c.c_void_p, c.c_int], None),
                            ("vosk_recognizer_free", [c.c_void_p], None),
                            ("vosk_recognizer_reset", [c.c_void_p], None),
                            ("vosk_recognizer_accept_waveform", [c.c_void_p, c.c_char_p, c.c_int], c.c_int),
                            ("vosk_recognizer_result", [c.c_void_p], c.c_char_p),
                            ("vosk_recognizer_partial_result", [c.c_void_p], c.c_char_p)):
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, res
    return lib


def said(raw, key):
    try:
        return str(json.loads(raw or b"{}").get(key) or "")
    except ValueError:
        return ""


def phrases(words, known):
    """The wake phrase, and with its greeting's twin ("hey potato", "hi potato"): those of their words the model
    knows, all of them."""
    out = [list(words)]
    if words and words[0] in SWAPS:
        out.append([SWAPS[words[0]]] + list(words[1:]))
    return [p for p in out if p and all(known(w) for w in p)]


def spotter(lib, model, wake, known):
    """A recognizer of the wake phrase alone (and everyday words, for whatever else it hears), its words timed and
    how sure it is of each: None when its model doesn't know the phrase's words."""
    if not wake:
        return None
    name = {w for p in wake for w in p if w not in SWAPS}       # (its greeting alone, said in a song, is a word too)
    grammar = [" ".join(p) for p in wake] + [w for w in EVERYDAY if w not in name and known(w)] + ["[unk]"]
    rec = lib.vosk_recognizer_new_grm(model, float(RATE), json.dumps(grammar).encode())
    if rec:
        lib.vosk_recognizer_set_words(rec, 1)
        lib.vosk_recognizer_set_partial_words(rec, 1)
    return rec or None


def spotted(raw, key, wake):
    """The wake phrase, heard by the spotter, and Vosk sure of each of its words."""
    try:
        ws = json.loads(raw or b"{}").get(key) or []
        words = [(str(w["word"]), float(w.get("conf", 0))) for w in ws]
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
    return any([w for w, _ in words[i:i + len(p)]] == p and min(c for _, c in words[i:i + len(p)]) >= SPOT_SURE
               for p in wake for i in range(len(words) - len(p) + 1))


def last_line(f):
    """The last thing arecord said (why it stopped)."""
    try:
        f.seek(0)
        lines = [ln.strip() for ln in f.read().decode(errors="replace").splitlines() if ln.strip()]
    except (OSError, ValueError):
        lines = []
    return lines[-1][:120] if lines else ""


def main(argv):
    if len(argv) < 4:
        say(error="hear.py <libvosk.so> <model folder> <microphone> [words...]")
        return 2
    lib_path, model_path, device, words = argv[1], argv[2], argv[3], argv[4:]
    try:
        lib = vosk(lib_path)
    except (OSError, AttributeError) as ex:
        say(error=f"Vosk wouldn't load ({ex})"[:160])
        return 2
    lib.vosk_set_log_level(-1)
    model = lib.vosk_model_new(model_path.encode())
    if not model:
        say(error="Its speech model wouldn't load: turn listening off and on again")
        return 2
    rec = lib.vosk_recognizer_new(model, float(RATE))

    def known(w):
        return lib.vosk_model_find_word(model, w.encode()) >= 0
    unknown = [w for w in words if not known(w)]
    wake = phrases(words, known)
    spot = None                                   # (made the first time something plays)
    cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"] + (["-D", device] if device else [])
    err = tempfile.TemporaryFile()                # (a file, not a pipe: arecord says something at every overrun)
    try:
        mic = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL)
    except OSError as ex:
        say(error=f"arecord wouldn't start ({ex.strerror or ex})")
        return 2
    say(ready=True, unknown=unknown)
    sound, told = mic.stdout.fileno(), sys.stdin.fileno()
    deaf, heard, odd, lines = False, "", b"", b""
    noisy, after, skip = False, 0.0, 0.0          # something playing; after the wake phrase over it, till then

    def fresh():
        nonlocal heard, odd, after
        lib.vosk_recognizer_reset(rec)
        if spot:
            lib.vosk_recognizer_reset(spot)
        heard, odd, after = "", b"", 0.0

    def free(data):
        """What's said, made out (as ever): what it's making out, then all of it at its end. (After the wake phrase,
        over music, till Pietato says it has what you said: "reset".)"""
        nonlocal heard
        if lib.vosk_recognizer_accept_waveform(rec, data, len(data)):
            text = said(lib.vosk_recognizer_result(rec), "text")
            if text or heard:
                say(final=text)
            heard = ""
        else:
            part = said(lib.vosk_recognizer_partial_result(rec), "partial")
            if part != heard:
                heard = part
                say(partial=part)
    try:
        while True:
            ready, _, _ = select.select([sound, told], [], [], 1.0)
            if told in ready:
                got = os.read(told, 4096)
                if not got:
                    return 0                      # (Pietato's gone)
                lines += got
                while b"\n" in lines:
                    line, lines = lines.split(b"\n", 1)
                    what = line.strip().decode(errors="replace")
                    if what == "quit":
                        return 0
                    if what in ("deaf", "listen", "reset"):
                        if what != "reset":
                            deaf = what == "deaf"
                        fresh()
                    elif what in ("noisy", "clear") and (what == "noisy") != noisy:
                        noisy = what == "noisy"
                        if noisy and spot is None:
                            spot = spotter(lib, model, wake, known)
                        if spot:
                            lib.vosk_recognizer_reset(spot)
            if sound in ready:
                data = os.read(sound, CHUNK)
                if not data:
                    mic.wait()
                    say(error=last_line(err) or "The microphone stopped")
                    return 1
                if deaf:
                    continue
                data, odd = odd + data, b""
                if len(data) % 2:                 # (whole samples only)
                    data, odd = data[:-1], data[-1:]
                now = time.monotonic()
                if after and now > after:         # (nothing said after the wake phrase, for a while)
                    after = 0.0
                if after and now < skip:          # (the music, as it goes quieter)
                    continue
                if not (noisy and spot) or after:
                    free(data)
                    continue
                if lib.vosk_recognizer_accept_waveform(spot, data, len(data)):   # over music: the wake phrase alone
                    heard_it = spotted(lib.vosk_recognizer_result(spot), "result", wake)
                else:
                    heard_it = spotted(lib.vosk_recognizer_partial_result(spot), "partial_result", wake)
                if heard_it:
                    say(final=" ".join(wake[0]))  # (Pietato listens for what you say next, the music quieter)
                    lib.vosk_recognizer_reset(spot)
                    lib.vosk_recognizer_reset(rec)
                    heard, after, skip = "", now + AFTER_MOST, now + AFTER_SKIP
    finally:
        try:
            mic.kill()
            mic.wait(3)
        except (OSError, subprocess.TimeoutExpired):
            pass
        lib.vosk_recognizer_free(rec)
        lib.vosk_model_free(model)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        sys.exit(0)
