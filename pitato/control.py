"""The web page's requests: a server on this Pi only (webui.py asks it), and the key it wants."""
import hmac
import json
import math
import os
import secrets
import threading
import urllib.parse

from .config import CONTROL_KEY, CONTROL_PORT, home_dir
from .bot import Friend
from .coder import CODER_CLIP_MAX
from .screens.sketch import sketch_image, SKETCH_BYTES


# ---- the web page's requests ----------------------------------------------------------
class Control:
    """Requests from the web page, handed to the main loop (it owns the screen and the player)
    and answered once done."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = []
        self.r, self.w = os.pipe()
        os.set_blocking(self.r, False)
        os.set_blocking(self.w, False)

    def ask(self, cmd, timeout=25):
        job = {"cmd": cmd, "done": threading.Event(), "out": None}
        with self.lock:
            self.jobs.append(job)
        try:
            os.write(self.w, b".")                     # wake the main loop
        except OSError:
            pass                                       # (the pipe is full: it's awake already)
        if job["done"].wait(timeout):
            return job["out"]
        with self.lock:
            if any(j is job for j in self.jobs):       # never started: forget it
                self.jobs = [j for j in self.jobs if j is not job]
                return {"error": "Media mode is busy. Try again in a moment"}
        job["done"].wait(timeout)                      # started: let it finish
        return job["out"] or {"error": "Media mode is busy. Try again in a moment"}

    def take(self):
        try:
            while os.read(self.r, 4096):
                pass
        except OSError:
            pass
        with self.lock:
            jobs, self.jobs = self.jobs, []
        return jobs

    @staticmethod
    def done(job, out):
        job["out"] = out
        job["done"].set()


def control_key():
    """A new key for the control server, in a file only root and you (the web page) can read."""
    key = secrets.token_hex(16)
    try:
        os.makedirs(os.path.dirname(CONTROL_KEY), mode=0o755, exist_ok=True)
        tmp = CONTROL_KEY + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        st = os.stat(home_dir())
        os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, CONTROL_KEY)
    except OSError as ex:
        print(f"couldn't save the web page's key: {ex}", flush=True)
    return key


def serve_control(media, control, port=CONTROL_PORT, key=None):
    """A small web server on this Pi only (127.0.0.1) for the web page (webui.py): what's on
    the screen, the lists, and requests to put things there. With a key, every request needs it."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def allowed(self):
            if not key or hmac.compare_digest((self.headers.get("X-Pitato-Key") or "").encode(), key.encode()):
                return True
            self.reply(401, {"error": "The web page's key doesn't match. Restart pitato-web."})
            return False

        def reply(self, code, body, ctype="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed():
                return
            u = urllib.parse.urlsplit(self.path)
            q = dict(urllib.parse.parse_qsl(u.query))
            try:
                if u.path == "/state":
                    return self.reply(200, media.web_state())
                if u.path == "/screen":
                    shot = media.web_screen()
                    if not shot:
                        return self.reply(403, {"error": "The terminal stays on the Pi's screen"})
                    return self.reply(200, shot[0], shot[1])
                if u.path == "/catalog":
                    return self.reply(200, media.web_catalog())
                if u.path == "/channels":
                    return self.reply(200, media.web_channels(q.get("what", "")))
                if u.path == "/radio":
                    return self.reply(200, media.web_radio(q.get("genre") or None, q.get("q") or None))
                if u.path == "/cameras":
                    return self.reply(200, media.web_cameras())
                if u.path == "/camframe":
                    jpeg = media.web_camframe(q.get("addr", ""))
                    return self.reply(200, jpeg, "image/jpeg") if jpeg else \
                        self.reply(404, {"error": "That camera isn't answering"})
                if u.path == "/friend":
                    return self.reply(200, media.web_friend())
                if u.path == "/computers":             # (asks a computer: here, not on the screen's thread)
                    return self.reply(200, media.web_computers(q.get("addr", "")))
                if u.path == "/coder":
                    return self.reply(200, media.coder_state())
                if u.path == "/bluetooth":
                    return self.reply(200, media.web_bluetooth())
                if u.path == "/friendpic":
                    pic = Friend.picture_bytes(q.get("id", ""))
                    return self.reply(200, pic, "image/jpeg") if pic else self.reply(404, {"error": "No such picture"})
                if u.path == "/icon":
                    icon = media.web_icon(q.get("name", ""), q.get("size") or 96)
                    return self.reply(200, icon, "image/png") if icon else self.reply(404, {"error": "No such app"})
            except Exception as ex:
                print(f"web page asked for {u.path}: {ex!r}", flush=True)
                return self.reply(500, {"error": "Something went wrong on the Pi"})
            self.reply(404, {"error": "Not found"})

        def coder_say(self, q):
            """A clip for the Bot to say at work: a WAV, answered once it's been said."""
            try:
                n = int(self.headers.get("Content-Length") or -1)
            except ValueError:
                n = -1
            if not 0 <= n <= CODER_CLIP_MAX:
                return self.reply(413, {"ok": False, "error": "clip too big (8 MB at most)"})
            data = self.rfile.read(n)
            try:
                code, out = media.coder_say(data, q.get("pose") or "talking")
            except Exception as ex:
                print(f"coder clip: {ex!r}", flush=True)
                code, out = 500, {"ok": False, "error": "Something went wrong on the Pi"}
            self.reply(code, out)

        def sketch(self):
            """A drawing from the web page's Draw tab (a PNG): opened here, then put on the screen."""
            try:
                n = int(self.headers.get("Content-Length") or -1)
            except ValueError:
                n = -1
            if not 0 < n <= SKETCH_BYTES:
                return self.reply(413, {"error": "That drawing is too big"})
            try:
                im = sketch_image(self.rfile.read(n))
            except ValueError as ex:
                return self.reply(400, {"error": str(ex)})
            self.reply(200, control.ask({"cmd": "sketch", "image": im}))

        def do_POST(self):
            if not self.allowed():
                return
            u = urllib.parse.urlsplit(self.path)
            if u.path == "/coder/say":
                return self.coder_say(dict(urllib.parse.parse_qsl(u.query)))
            if u.path == "/sketch":
                return self.sketch()
            if u.path == "/coder/prompts":               # your agent asks for prompts: waits a while for one
                q = dict(urllib.parse.parse_qsl(u.query))
                try:
                    wait, got = float(q.get("wait") or 0), int(q.get("got") or 0)
                except ValueError:
                    return self.reply(400, {"ok": False, "error": "wait is seconds, got is a prompt's number"})
                if not math.isfinite(wait):
                    wait = 0.0
                try:
                    return self.reply(200, media.prompts.take(wait, got, q.get("run") or ""))
                except Exception as ex:
                    print(f"prompts: {ex!r}", flush=True)
                    return self.reply(500, {"ok": False, "error": "Something went wrong on the Pi"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if not 0 <= n <= 1 << 20:
                return self.reply(413, {"error": "Too big"})
            if "json" not in (self.headers.get("Content-Type") or ""):
                return self.reply(415, {"error": "JSON only"})
            try:
                cmd = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                cmd = None
            if not isinstance(cmd, dict):
                return self.reply(400, {"error": "Bad request"})
            cmd["cmd"] = u.path.strip("/")
            if cmd["cmd"] == "computer":               # another computer's files: it can take a while, so here
                try:
                    return self.reply(200, media.web_computer(cmd))
                except Exception as ex:
                    print(f"computer: {ex!r}", flush=True)
                    return self.reply(500, {"error": "Something went wrong on the Pi"})
            if cmd["cmd"] == "show" and isinstance(cmd.get("path"), str):
                media.web_show_look(cmd["path"])       # (another computer's file: looked at here, not on the screen's thread)
            if cmd["cmd"] == "bluetooth":              # (Bluetooth does it on threads of its own: answered at once)
                try:
                    return self.reply(200, media.web_bluetooth_do(cmd))
                except Exception as ex:
                    print(f"bluetooth: {ex!r}", flush=True)
                    return self.reply(500, {"error": "Something went wrong on the Pi"})
            if cmd["cmd"] == "coder":                  # your agent's word: answered at once, off the main loop
                try:
                    return self.reply(200, media.web_coder(cmd))
                except Exception as ex:
                    print(f"coder: {ex!r}", flush=True)
                    return self.reply(500, {"ok": False, "error": "Something went wrong on the Pi"})
            self.reply(200, control.ask(cmd))

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as ex:
        print(f"the web page can't work the screen: {ex}", flush=True)
        return None
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="control").start()
    return server
