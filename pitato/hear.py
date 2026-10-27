#!/usr/bin/env python3
"""hear.py - the bot's ears: a USB microphone, made sense of by Vosk on the Pi itself.

Pie-tato (pitato/listen.py) runs this as you rather than as root, as it does Piper: what it reads, a speech model,
comes from the internet. It records with arecord and says what it makes out, a line of JSON at a time:
    {"ready": true, "unknown": [...]}   its model is loaded (and the words of yours it doesn't know)
    {"partial": "..."}                  what's being said, so far
    {"final": "..."}                    something said, at its end
    {"error": "..."}                    it can't go on (and it stops)
It's told, a line at a time: "deaf" (what it hears is let go, unheard: the bot is speaking, say), "listen",
"reset" (what it was making out, forgotten) and "quit". Only Python's own modules: it runs with -I.

    python3 -I hear.py <libvosk.so> <model folder> <microphone, or ""> [words it should know...]
"""
import ctypes
import json
import os
import select
import subprocess
import sys
import tempfile

RATE = 16000
CHUNK = 4000             # bytes at a time: an eighth of a second


def say(**what):
    try:
        sys.stdout.write(json.dumps(what) + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        raise SystemExit(0)                       # (Pie-tato's gone: so is this)


def vosk(path):
    """Vosk's library, with what's used of it."""
    lib = ctypes.CDLL(path)
    c = ctypes
    for name, args, res in (("vosk_set_log_level", [c.c_int], None),
                            ("vosk_model_new", [c.c_char_p], c.c_void_p),
                            ("vosk_model_free", [c.c_void_p], None),
                            ("vosk_model_find_word", [c.c_void_p, c.c_char_p], c.c_int),
                            ("vosk_recognizer_new", [c.c_void_p, c.c_float], c.c_void_p),
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
    unknown = [w for w in words if lib.vosk_model_find_word(model, w.encode()) < 0]
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
    try:
        while True:
            ready, _, _ = select.select([sound, told], [], [], 1.0)
            if told in ready:
                got = os.read(told, 4096)
                if not got:
                    return 0                      # (Pie-tato's gone)
                lines += got
                while b"\n" in lines:
                    line, lines = lines.split(b"\n", 1)
                    what = line.strip().decode(errors="replace")
                    if what == "quit":
                        return 0
                    if what in ("deaf", "listen", "reset"):
                        if what != "reset":
                            deaf = what == "deaf"
                        lib.vosk_recognizer_reset(rec)
                        heard, odd = "", b""
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
