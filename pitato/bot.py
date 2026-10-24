"""The bot: a model on another computer, through Ollama."""
import glob
import io
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .config import clean_name, read_config, read_own_bytes
from .util import UA
from .net import OLLAMA_OPENER, read_capped


# ---- the bot: a model on another computer, through Ollama ---------------------------------------------
FRIEND_LOG = "/var/lib/pitato/friend.json"   # what was said (root only)
FRIEND_PICS = "/var/lib/pitato/bot-pictures"  # the pictures in the conversation, small (root only)
FRIEND_PIC_SIZE = 480            # pixels across, at most, of a picture kept in the conversation
FRIEND_SEE_SIZE = 768            # ...and of one a model is shown
FRIEND_PIC_BYTES = 40 << 20      # a picture file bigger than this isn't opened
FRIEND_PIC_KINDS = ("JPEG", "PNG", "GIF", "BMP", "WEBP", "TIFF")   # ...nor any other kind
FRIEND_PIC_PIXELS = {"JPEG": 60_000_000, "MPO": 60_000_000,   # ...nor one bigger than this: a JPEG opens
                     "WEBP": 4_000_000}
FRIEND_PIC_OTHER = 16_000_000                                 # small, the rest open whole
FRIEND_PIC_ROOM = 64 << 20       # a picture it takes leaves this much room on the card
FRIEND_BUBBLE = (220, 165)       # a picture in the Bot page's conversation, at most
FRIEND_TIMEOUT = 180             # a big model asleep on the other computer can take a minute or more
FRIEND_KEEP = 60                 # lines of the conversation kept
FRIEND_LIMIT = 320               # characters of an answer: a few sentences fit the screen
FRIEND_ANSWER_MAX = 4_000_000    # bytes: more than this isn't Ollama answering
FRIEND_HELLO_AFTER = 1800        # opened after this long quiet: it says hello
FRIEND_HEAD = ("# Bot: a computer on your network running Ollama. On that computer Ollama has to\n"
               "# listen on the network (OLLAMA_HOST=0.0.0.0). Settings > Bot sets these too.\n")
FRIEND_PERSONA = ("You are a friendly little bot who lives on a small handheld screen: a Raspberry Pi "
                  "in a game-console case. Reply in one to three short sentences, as it has to fit on that "
                  "screen. Plain text: no emoji, no quotation marks, no markdown, no stage directions.")
FRIEND_LOOK = ("see", "look", "looking", "camera", "in front of you", "around you", "wearing", "holding",
               "room", "what is this", "what's this", "colour", "color")
FRIEND_TOPICS = ["weather", "weather", "time", "time", "anything", "anything", "markets", "playing"]
FRIEND_SIGHT = 4                 # ...and with a camera and a model that can see, this many of what it sees
# asked for a picture: "take a picture", "snap a quick pic of the garage", "grab a couple of photos",
# "get me a picture of the door", "send me a photo", "selfie!", and "another one" just after one
# (not "take a look at this picture", "did you take my picture down", "I'll send you a photo",
# "please don't take my picture", "why did you take that picture?")
FRIEND_SNAP_WHAT = r"(?:picture|photo|pic|snapshot|selfie|image|snap)s?"
FRIEND_SNAP_FILL = (r"(?:(?:a|an|another|one|more|me|us|the|this|that|my|our|your|some|few|couple|of|several|two|"
                    r"three|\d+|second|third|quick|new|fresh|live|current|latest|nice|good|better|clear|clearer|proper|"
                    r"real|little|big|wide|close-up|closeup|group)\s+){0,4}")
FRIEND_SNAP = re.compile(
    r"\b(?:take|snap|shoot|capture|grab)\s+" + FRIEND_SNAP_FILL + FRIEND_SNAP_WHAT + r"\b(?!\s+(?:down|off|away|back)\b)"
    r"|\bsnap\s+(?:a|another|one|some)\s+(?:quick\s+)?shots?\b"
    r"|\b(?:get|send)\s+(?:me|us)\s+" + FRIEND_SNAP_FILL + FRIEND_SNAP_WHAT + r"\b"
    r"|\bphotograph\s+(?:me|us|it|this|that|the|my|our)\b"
    r"|^\W*(?:(?:a|another)\s+)?(?:selfie|picture|photo|pic|snapshot)(?:\s+please)?\W*$|^\W*say\s+cheese\W*$", re.I)
FRIEND_SNAP_NO = {"don't", "dont", "never", "not", "stop", "quit", "did", "didn't", "didnt", "does", "doesn't",
                  "won't", "wont", "shouldn't", "mustn't", "when", "whenever"}   # ...just before it: not asking
FRIEND_SNAP_AGAIN = re.compile(                  # just after a picture: "take another one", "one more", "try again"
    r"^\W*(?:(?:ok|okay|now|please|great|nice|cool|thanks)\W+)*(?:(?:take|snap|grab|get)\s+(?:me\s+)?)?"
    r"(?:another(?:\s+one)?|one\s+more|a\s+new\s+one|(?:try\s+|do\s+it\s+)?again)(?:\s+please)?\W*$", re.I)
FRIEND_ASKS = {
    "hello": "They just opened your screen. Greet them, and say one thing about right now.",
    "weather": "Say something about the weather.",
    "time": "Say something about the time of day.",
    "markets": "Say something about how the stocks and coins are doing.",
    "playing": "Say something about what's playing.",
    "anything": "Say one thing about right now.",
    "sight": ("Say something about what you see, in a sentence or two: who or what is there, or what's "
              "different from last time. Don't list everything."),
    "describe": ("They asked what you see. Describe it in two or three short sentences, the way you'd "
                 "say it out loud: who or what is there and what's going on. No lists."),
}
FRIEND_CHATTER = [("Every 30 min", "30"), ("Every hour", "60"), ("Never", "0")]
FRIEND_PAGES = ("friend", "f_models", "f_eyes", "f_voices")   # Settings > Bot and its lists
# its face follows the tone of what it said: PiE-ink's faces and words
FRIEND_FACES = {"happy": "(◕‿◕)", "pleased": "(•‿‿•)", "cool": "(⌐■_■)", "curious": "(☉_☉)",
                "sorry": "(╥_╥)", "worried": "(°▃▃°)", "sleepy": "(⇀‿‿↼)", "thinking": "(•_•)",
                "plain": "(•‿•)", "surprised": "(⊙o⊙)"}
FRIEND_GOOD = ("glad", "lovely", "great", "nice", "good", "happy", "yes", "sure", "thanks", "thank",
               "wonderful", "excellent", "perfect", "enjoy", "fun", "delight", "warm", "sunny", "well",
               "finally", "clear", "bright", "ready", "cheer", "love", "best", "better")
FRIEND_BAD = ("cold", "wet", "grim", "dull", "miserable", "tired", "bad", "wrong", "trouble", "problem",
              "miss", "late", "busy", "stuck", "dark", "grey", "gray")
FRIEND_SORRY = ("sorry", "afraid", "unfortunately", "sadly", "can't", "cannot", "don't know", "no idea")
FRIEND_SLEEPY = ("sleep", "bed", "dream", "yawn", "goodnight", "good night", "nap")
FRIEND_THINK = re.compile(r"<think>.*?</think>|<thinking>.*?</thinking>", re.S | re.I)


def friend_face(text, kind="", busy=False):
    """(face, mood) for what it last said: good and gloomy words weighed against each other."""
    low = (text or "").lower()
    if busy:
        mood = "thinking"
    elif kind == "error":
        mood = "sorry"
    elif not low:
        mood = "plain"
    else:
        words = set(re.findall(r"[a-z']+", low))

        def has(ws):
            return any((w in low) if " " in w else (w in words) for w in ws)
        score = sum(w in words for w in FRIEND_GOOD) - sum(w in words for w in FRIEND_BAD)
        if has(FRIEND_SORRY):
            mood = "sorry"
        elif has(FRIEND_SLEEPY):
            mood = "sleepy"
        elif low.rstrip().endswith("?"):
            mood = "curious"
        elif score >= 2 or ("!" in low and score >= 1):
            mood = "cool"
        elif score >= 1:
            mood = "happy"
        elif score <= -2:
            mood = "worried"
        elif kind == "chat":
            mood = "pleased"
        else:
            mood = "plain"
    return FRIEND_FACES[mood], mood


def friend_wants_eyes(text):
    """Does this sound like a question about what's in front of the camera?"""
    low = (text or "").lower()
    words = set(re.findall(r"[a-z']+", low))
    return any((w in low) if " " in w else (w in words) for w in FRIEND_LOOK)


def friend_wants_photo(text):
    """Does this ask for a picture to be taken? (Not when it says not to, or asks about one taken.)"""
    low = (text or "").lower().replace("\u2019", "'")
    for m in FRIEND_SNAP.finditer(low):
        said = re.split(r"[.,!?;:]", low[:m.start()])[-1]          # what comes just before it, in that sentence
        said = re.sub(r"\b(?:don'?t|wouldn'?t)\s+mind\b", " ", said)
        if re.search(r"\bwhy\s+(?:don'?t\s+you|not)\s*$", said):    # a suggestion: "why don't you take one?"
            return True
        words = re.findall(r"[a-z0-9']+", said)[-4:]
        if FRIEND_SNAP_NO.intersection(words) or words[-2:] in (["do", "you"], ["can", "it"]):
            continue
        return True
    return False


def friend_image(src):
    """A picture for the bot, from its bytes or a file of yours: upright, in colour, no bigger than a
    model needs. ValueError when it can't be opened."""
    import warnings
    from PIL import Image, ImageOps
    try:
        data = read_own_bytes(src, FRIEND_PIC_BYTES) if isinstance(src, str) else src
        with warnings.catch_warnings():               # (its size is looked at here, before it's opened)
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(data or b""), formats=FRIEND_PIC_KINDS)
        if im.width * im.height > FRIEND_PIC_PIXELS.get(im.format, FRIEND_PIC_OTHER):
            raise ValueError("That picture is too big")
        k = FRIEND_SEE_SIZE * 2 / max(im.size)
        if k < 1:                                       # (a JPEG opens smaller, quickly: a long one too)
            im.draft("RGB", (max(1, int(im.width * k)), max(1, int(im.height * k))))
        if im.mode not in ("RGB", "RGBA", "L", "LA"):
            im = im.convert("RGBA" if "transparency" in im.info or im.mode == "PA" else "RGB")
        im.thumbnail((FRIEND_SEE_SIZE, FRIEND_SEE_SIZE))   # small first, then the rest
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA"):                   # see-through parts on white
            flat = Image.new("RGB", im.size, (255, 255, 255))
            flat.paste(im.convert("RGBA"), mask=im.convert("RGBA").getchannel("A"))
            im = flat
        return im.convert("RGB") if im.mode != "RGB" else im
    except Exception as ex:                         # (not a picture, or a broken one)
        if isinstance(ex, ValueError) and str(ex).startswith("That picture"):
            raise
        raise ValueError("That picture can't be opened")


def friend_tidy(text, limit=FRIEND_LIMIT):
    """An answer made fit for the screen: no reasoning, no markdown, no quotes, one paragraph."""
    text = FRIEND_THINK.sub(" ", text or "")
    text = re.sub(r"^\s*<think>.*", "", text, flags=re.S | re.I).strip()
    for junk in ("```", "**", "*", "__", "#"):
        text = text.replace(junk, "")
    line = " ".join(ln.strip() for ln in text.splitlines() if ln.strip()).strip('"“”\' ')
    if len(line) > limit:
        line = line[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return line


def ollama_url(server):
    """http://address:11434 from what was typed: an address or a name, a port or not. Only the
    machine and the port are kept: Ollama's calls are always at the top."""
    t = (server or "").strip()
    if not t:
        return ""
    if not t.startswith(("http://", "https://")):
        t = "http://" + t
    try:
        u = urllib.parse.urlsplit(t)
        host, port = u.hostname, u.port
    except ValueError:
        return ""
    if not host:
        return ""
    return f"{u.scheme}://{f'[{host}]' if ':' in host else host}:{port or 11434}"


class OllamaError(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


class CantSee(ValueError):
    """The model was shown a picture, and can't look at pictures."""

    def __init__(self, model):
        super().__init__(f"{model} can't look at pictures. Choose a model that can see in Settings > Bot")
        self.model = model


def ollama_call(server, path, body=None, timeout=FRIEND_TIMEOUT):
    url = ollama_url(server)
    if not url:
        raise ValueError("That isn't an address. Try 192.168.1.20")
    where = url.split("://", 1)[-1]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json", **UA})
    try:
        with OLLAMA_OPENER.open(req, timeout=timeout) as r:
            got = json.loads(read_capped(r, FRIEND_ANSWER_MAX, time.monotonic() + timeout) or b"{}")
        if not isinstance(got, dict):
            raise ValueError("not Ollama")
        return got
    except urllib.error.HTTPError as e:
        try:
            detail = clean_name(json.loads(e.read(65536) or b"{}").get("error"), 200)
        except (ValueError, OSError, AttributeError):
            detail = ""
        raise OllamaError(e.code, detail or f"Ollama said {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason):
            raise ValueError(f"No answer from {where} in {timeout} s. A big model can take longer")
        raise ValueError(f"Can't reach {where}. Is Ollama on there, and listening on the network?")


def ollama_sees(server, model, timeout=6):
    """True when Ollama says the model can see, False when it says it can't, None when it doesn't
    say (an older Ollama)."""
    got = ollama_call(server, "/api/show", {"model": model, "name": model}, timeout=timeout)
    caps = got.get("capabilities")
    return ("vision" in caps) if isinstance(caps, list) else None


def ollama_models(server, timeout=6):
    got = ollama_call(server, "/api/tags", timeout=timeout)
    return sorted({m.get("name", "") for m in got.get("models", []) if isinstance(m, dict) and m.get("name")})


def ollama_deciders(server, timeout=6):
    """The decision models on that computer: those Ollama (0.35 or newer) says can decide ("decision"
    among what /api/show says a model can do). They're asked at /v1/systemone, not chatted with."""
    found = []
    for name in ollama_models(server, timeout):
        try:
            caps = ollama_call(server, "/api/show", {"model": name, "name": name}, timeout=timeout).get("capabilities")
        except OllamaError:
            continue
        if isinstance(caps, list) and "decision" in caps:
            found.append(name)
    return found


def ollama_decide(server, model, state, instructions, choices, timeout):
    """A decision model's pick of choices ({key: what it means}), given state (text, or an object it
    reads as JSON): (key, how sure it is, 0 to 1)."""
    body = {"model": model, "state": state, "keep_alive": "30m",
            "questions": {"pick": {"type": "choice", "instructions": instructions, "criteria": choices}}}
    try:
        got = ollama_call(server, "/v1/systemone", body, timeout)
    except OllamaError as e:
        if e.code == 404 and "model" not in e.detail.lower():
            raise ValueError("That computer's Ollama is too old for decision models (0.35 or newer)")
        if e.code == 404:
            raise ValueError(f"That computer doesn't have {model}")
        raise ValueError(f"{model} couldn't decide: {e.detail}")
    answer = (got.get("answers") or {}).get("pick") or {}
    pick = answer.get("choice")
    if pick not in choices:
        raise ValueError(f"{model} didn't pick one of the moves")
    sure = answer.get("confidence")
    return pick, float(sure) if isinstance(sure, (int, float)) and not isinstance(sure, bool) else None


def ollama_generate(server, model, system, prompt, images=None, timeout=FRIEND_TIMEOUT):
    """One answer, the same way PiE-ink asks: no reasoning pass, kept warm for the next one."""
    body = {"model": model, "prompt": prompt, "system": system, "stream": False, "think": False,
            "keep_alive": "30m", "options": {"temperature": 0.8, "num_predict": 300}}
    if images:
        body["images"] = images

    def ask():
        try:
            return ollama_call(server, "/api/generate", body, timeout)
        except OllamaError as e:
            low = e.detail.lower()
            if e.code == 400 and "think" in low and "think" in body:
                raise                                 # (asked again, below)
            if e.code == 404:
                raise ValueError(f"That computer doesn't have {model}. Pick another in Settings > Bot")
            if images and any(w in low for w in ("image", "vision", "multimodal")):
                raise CantSee(model)
            raise
    try:
        out = ask()
    except OllamaError as e:
        if not (e.code == 400 and "think" in e.detail.lower()):
            raise
        body.pop("think", None)                       # an older Ollama, or a model that doesn't think
        out = ask()
    text = friend_tidy(out.get("response", ""))
    if text:
        return text
    if (out.get("thinking") or "").strip():          # it spent the whole answer thinking: again, plainly
        body.pop("think", None)
        body["options"] = dict(body["options"], num_predict=-1)
        body["prompt"] = prompt + "\n\nAnswer directly. Do not show your reasoning."
        text = friend_tidy(ask().get("response", ""))
        if text:
            return text
        raise ValueError(f"{model} only gave its reasoning. Try another model")
    raise ValueError(f"{model} said nothing")


class Friend:
    """The bot: its settings (bot.txt), what it knows right now (from media mode),
    and the conversation, kept on disk. One answer at a time, asked for in the background."""

    def __init__(self):
        self.conf = {}
        self.log = []                # [{"who": "you"/"friend", "text", "t", "kind": "chat"/"remark"/"error"}]
        self.busy = False
        self.models, self.models_at, self.models_status = [], "", ""
        self.on_change = lambda: None
        self.facts = lambda: []      # lines of what's true right now
        self.look = lambda text="": (None, "there's no camera")   # (a picture's bytes, whose) or (None, why not)
        self.snap = self.no_camera   # a picture taken: (where it's saved, its bytes, whose) or ValueError
        self.on_reply = lambda text: None
        self.doing = ""              # what it's busy with: "Taking a picture…", "Looking…"
        self.vision = {}             # model -> it can see (True / False), as Ollama said, or as it went
        self.vision_asked = {}       # model -> when Ollama was last asked
        self.lock = threading.Lock()
        self.load_log()

    def load(self, patterns):
        if not any(glob.glob(p) for p in patterns):        # not moved over yet: its earlier name
            patterns = [os.path.join(os.path.dirname(p), "friend.txt") for p in patterns]
        self.conf = read_config(patterns)

    @property
    def server(self):
        return (self.conf.get("server") or "").strip()

    @property
    def model(self):
        return (self.conf.get("model") or "").strip()

    @property
    def eyes(self):
        return (self.conf.get("eyes") or "").strip()

    @property
    def name(self):
        return (self.conf.get("name") or "").strip()[:40]

    def ready(self):
        return bool(self.server and self.model)

    def chatter(self):
        """Minutes between remarks of its own; 0: never."""
        v = (self.conf.get("chatter") or "30").strip().lower()
        if v in ("never", "off", "no"):
            return 0
        try:
            n = float(v)
        except ValueError:
            return 30
        if n != n or abs(n) == float("inf"):          # (nan, inf)
            return 30
        return int(max(0, min(1440, n)))

    def chatter_text(self):
        n = self.chatter()
        return next((t for t, v in FRIEND_CHATTER if int(v) == n), f"Every {n} min")

    # the conversation, kept between start-ups
    def load_log(self):
        try:
            with open(FRIEND_LOG) as f:
                got = json.load(f)
            self.log = [x for x in got if isinstance(x, dict) and (x.get("text") or x.get("pic"))][-FRIEND_KEEP:]
        except (OSError, ValueError, TypeError):
            self.log = []

    def save_log(self):
        try:
            os.makedirs(os.path.dirname(FRIEND_LOG), exist_ok=True)
            tmp = FRIEND_LOG + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self.log[-FRIEND_KEEP:], f)
            os.replace(tmp, FRIEND_LOG)
        except OSError as ex:
            print(f"couldn't keep the conversation: {ex}", flush=True)
        keep = {x.get("pic") for x in list(self.log)}
        try:
            with os.scandir(FRIEND_PICS) as it:            # pictures no longer in it go (not one just made)
                for en in it:
                    if en.name.endswith(".jpg") and en.name[:-4] not in keep and \
                            time.time() - en.stat().st_mtime > 60:
                        os.remove(en.path)
        except OSError:
            pass

    def add(self, who, text, kind, **more):
        """A line of the conversation; more: pic (a picture kept with it), photo (where the picture
        is in Photos), seen (the camera it looked through)."""
        with self.lock:
            self.log.append(dict({"who": who, "text": text, "t": time.time(), "kind": kind},
                                 **{k: v for k, v in more.items() if v}))
            self.log = self.log[-FRIEND_KEEP:]
        self.save_log()
        self.on_change()

    @staticmethod
    def no_camera(text=""):
        raise ValueError("there's no camera")

    # pictures in the conversation
    def keep_picture(self, im):
        """A small copy of a picture, kept with the conversation: its id."""
        os.makedirs(FRIEND_PICS, mode=0o700, exist_ok=True)
        pid = uuid.uuid4().hex[:16]
        small = im.copy()
        small.thumbnail((FRIEND_PIC_SIZE, FRIEND_PIC_SIZE))
        path = os.path.join(FRIEND_PICS, pid + ".jpg")
        small.save(path + ".part", "JPEG", quality=82)
        os.replace(path + ".part", path)
        return pid

    @staticmethod
    def picture_bytes(pid):
        """One of the conversation's pictures, as JPEG: None when there's no such picture."""
        if not re.fullmatch(r"[0-9a-f]{16}", str(pid or "")):
            return None
        try:
            with open(os.path.join(FRIEND_PICS, pid + ".jpg"), "rb") as f:
                return f.read(FRIEND_PIC_BYTES)
        except OSError:
            return None

    @staticmethod
    def for_model(im):
        """A picture as a model is shown it: base64 JPEG."""
        import base64
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()

    def sees(self):
        """It can look at pictures: a model for its eyes, or one Ollama says can see (and neither
        found it can't)."""
        model = self.eyes or self.model
        if self.vision.get(model) is False:
            return False
        return bool(self.eyes) or self.vision.get(model) is True

    def check_vision(self):
        """Whether the model it looks with can see, asked of Ollama in the background (once in a while)."""
        model, server = self.eyes or self.model, self.server
        if not (model and server) or model in self.vision \
                or time.time() - self.vision_asked.get(model, 0) < 600:
            return
        self.vision_asked[model] = time.time()

        def job():
            try:
                got = ollama_sees(server, model)
            except Exception:
                return                                  # (not now: asked again in a while)
            if got is not None:
                self.vision[model] = got
                self.on_change()
        threading.Thread(target=job, daemon=True, name="friend-vision").start()

    def clear(self):
        with self.lock:
            self.log = []
        self.save_log()
        self.on_change()

    def last_said(self):
        return self.log[-1]["t"] if self.log else 0.0

    def face(self):
        last = next((x for x in reversed(self.log) if x["who"] == "friend"), None)
        return friend_face(last["text"] if last else "", last["kind"] if last else "", self.busy)

    # asking it
    def start(self):
        with self.lock:
            if self.busy:
                return False
            self.busy = True
        self.on_change()
        return True

    def say(self, text, picture=None):
        """You said something (and sent a picture: a file of yours, perhaps); it answers in the
        background. False while it's on the last one."""
        text = " ".join((text or "").split())[:400]
        if not (text or picture) or not self.start():
            return False
        if picture is None:
            self.add("you", text, "chat")
        else:
            self.doing = "Looking…"                    # (your line comes once the picture is open)
        threading.Thread(target=self.job, args=(text, None, picture), daemon=True, name="friend").start()
        return True

    def remark(self, topic="anything"):
        """Something of its own, about right now."""
        if not self.ready() or not self.start():
            return False
        threading.Thread(target=self.job, args=(None, topic), daemon=True, name="friend").start()
        return True

    def describe(self, look, done=lambda text, error: None):
        """It looks through the camera you chose and says what it sees (the Camera tab's SELECT, the
        web page's Describe): look() gives (a JPEG, the camera) or (None, why not), and done(what it
        said, or None; why it couldn't, or None) comes after. False while it's on the last one."""
        if not self.start():
            return False
        self.doing = "Looking…"
        threading.Thread(target=self.describe_job, args=(look, done), daemon=True, name="friend").start()
        return True

    def describe_job(self, look, done):
        text, error = None, None
        try:
            if not self.server:
                raise ValueError("I'm not set up yet. Put your Ollama computer in Settings > Bot")
            if not self.model:
                raise ValueError("Pick a model for me in Settings > Bot")
            model = self.eyes or self.model
            if self.vision.get(model) is False:
                raise CantSee(model)
            got, note = look()
            if not got:
                raise ValueError(f"I can't see anything: {note}")
            try:
                im = friend_image(got)
            except ValueError:
                raise ValueError("I can't see anything: the camera's picture was broken")
            pid = self.keep_picture(im)
            lines = []
            try:
                lines += list(self.facts())
            except Exception as ex:
                print(f"the bot couldn't look around: {ex!r}", flush=True)
            lines.append(f"The attached picture is what the camera ({note}) sees right now.")
            text = ollama_generate(self.server, model, self.system(),
                                   "\n".join(lines) + "\n\n" + FRIEND_ASKS["describe"], [self.for_model(im)])
            self.vision.setdefault(model, True)
            self.add("friend", text, "remark", pic=pid, seen=note)
        except CantSee as ex:
            self.vision[ex.model] = False
            text, error = None, str(ex)[:200]
            self.add("friend", error, "error")
        except Exception as ex:
            text, error = None, str(ex)[:200] or "That didn't work"
            self.add("friend", error, "error")
        finally:
            try:
                done(text, error)                      # (said out loud before it's free again)
            except Exception as ex:
                print(f"after the bot looked: {ex!r}", flush=True)
            with self.lock:
                self.busy = False
                self.doing = ""
            self.on_change()

    def job(self, message, topic, picture=None):
        try:
            sent = None
            if picture is not None:                    # your picture: in the conversation first
                try:
                    im = friend_image(picture)
                except (ValueError, OSError) as ex:
                    if message:
                        self.add("you", message, "chat")
                    raise ValueError(str(ex) if isinstance(ex, ValueError) else "That picture can't be opened")
                pid = self.keep_picture(im)
                self.add("you", message, "chat", pic=pid, photo=picture)
                sent = self.for_model(im)
            if not self.server:
                raise ValueError("I'm not set up yet. Put your Ollama computer in Settings > Bot")
            if not self.model:
                raise ValueError("Pick a model for me in Settings > Bot")
            if message and picture is None and (friend_wants_photo(message) or
                                                 self.after_photo() and FRIEND_SNAP_AGAIN.search(message)):
                return self.photo(message)
            prompt, images, seen = self.prompt(message, topic, sent)
            model = self.eyes if images and self.eyes else self.model
            self.doing = "Thinking…"
            self.on_change()
            text = ollama_generate(self.server, model, self.system(), prompt, images)
            self.add("friend", text, "chat" if message or sent else "remark",
                     pic=seen[0] if seen else None, seen=seen[1] if seen else None)
            self.on_reply(text)
        except CantSee as ex:
            self.vision[ex.model] = False
            self.add("friend", str(ex)[:200], "error")
        except Exception as ex:
            self.add("friend", str(ex)[:200] or "That didn't work", "error")
        finally:
            with self.lock:
                self.busy = False
                self.doing = ""
            self.on_change()

    def after_photo(self):
        """The last thing it said was a picture it took (or why it couldn't take one)."""
        last = next((x for x in reversed(self.log) if x["who"] == "friend"), None)
        return bool(last) and (last.get("kind") == "photo" or last.get("kind") == "error"
                               and last.get("text", "").startswith("I couldn't take a picture"))

    def photo(self, message):
        """They asked for a picture: the camera takes one (into Photos too), and it's shown here,
        with a word on it from a model that can see."""
        self.doing = "Taking a picture…"
        self.on_change()
        try:
            path, data, cam = self.snap(message)
            im = friend_image(data)
        except Exception as ex:
            self.add("friend", f"I couldn't take a picture: {str(ex)[:150] or 'no answer'}", "error")
            return
        pid = self.keep_picture(im)
        text = f"Here's the picture from {cam}. It's in Photos too."
        model = self.eyes or self.model
        if self.vision.get(model) is not False:
            self.doing = "Looking…"
            self.on_change()
            lines = self.context(message)
            lines.append(f"{self.name} now says: {message}" if self.name else f"They now say: {message}")
            lines.append(f"So you took the attached picture with the camera ({cam}). It's saved in Photos.")
            try:
                text = ollama_generate(self.server, model, self.system(), "\n".join(lines) + "\n\nTell them you "
                                       "took it, and say something about what's in it, answering what they asked.",
                                       [self.for_model(im)])
                self.vision.setdefault(model, True)
            except CantSee:
                self.vision[model] = False
            except Exception as ex:
                print(f"the bot couldn't look at the picture: {ex}", flush=True)
        self.add("friend", text, "photo", pic=pid, photo=path, seen=cam)
        self.on_reply(text)

    def system(self):
        persona = (self.conf.get("persona") or "").strip() or FRIEND_PERSONA
        return persona + (f" The person you live with is called {self.name}." if self.name else "")

    def context(self, message):
        """What's true right now, and the last few lines said."""
        lines = []
        try:
            lines += list(self.facts())
        except Exception as ex:
            print(f"the bot couldn't look around: {ex!r}", flush=True)
        said = [x for x in self.log if x.get("kind") in ("chat", "remark", "photo")]
        if message is not None and said and said[-1]["who"] == "you":
            said = said[:-1]                          # (what you just said, or sent, goes last)
        if said[-6:]:
            lines.append("The conversation so far:")
            for x in said[-6:]:
                what = x.get("text") or ""
                if x.get("pic"):
                    what = ("[sent a picture] " if x["who"] == "you" else
                            "[took a picture] " if x.get("kind") == "photo" else "[looking through the camera] ") + what
                lines.append(("  They said: " if x["who"] == "you" else "  You said: ") + what[:200])
        return lines

    def look_now(self, text=""):
        """A picture from the camera for a model to look at: ((its id here, the camera), base64) or
        (None, why not)."""
        got, note = self.look(text)
        if not got:
            return None, note
        try:
            im = friend_image(got)
        except ValueError:
            return None, "the camera's picture was broken"
        return ((self.keep_picture(im), note), self.for_model(im)), note

    def prompt(self, message, topic, sent=None):
        """What's true right now, the last few lines said, and what to answer; the pictures it's
        shown; and the one it looked at (its id, the camera), if it did."""
        lines = self.context(message if message or sent else None)
        images, seen = None, None
        who = self.name or "They"
        if sent:
            images = [sent]
            lines.append(f"{who} sent you the attached picture.")
            lines.append(f"{who} now say{'s' if self.name else ''}: {message}" if message else
                         "They didn't say anything with it.")
            ask = ("Reply to them about the picture, carrying on from what was already said." if message
                   else "Say something about the picture.")
        elif message:
            if friend_wants_eyes(message):
                got, note = self.look_now(message)
                if got:
                    seen, images = got[0], [got[1]]
                    lines.append(f"The attached picture is what the camera ({note}) sees right now.")
                else:
                    lines.append(f"You can't see anything right now ({note}); say so if they asked.")
            lines.append(f"{self.name} now says: {message}" if self.name else f"They now say: {message}")
            ask = "Reply to them, carrying on from what was already said."
        else:
            if topic == "sight":
                got, note = self.look_now()
                if got:
                    seen, images = got[0], [got[1]]
                    lines.append(f"The attached picture is what the camera ({note}) sees right now.")
                    last = next((x for x in reversed(self.log) if x.get("seen") and x["who"] == "friend"), None)
                    if last and time.time() - last["t"] < 6 * 3600:
                        mins = max(1, int((time.time() - last["t"]) // 60))
                        lines.append(f"When you last looked, {mins} minutes ago, you said: {last['text'][:200]}")
                else:
                    topic = "anything"                 # nothing to see: something else, then
            ask = FRIEND_ASKS.get(topic, FRIEND_ASKS["anything"])
        return "\n".join(lines) + "\n\n" + ask, images, seen

    def fetch_models(self, server=None):
        """The models on the Ollama computer, asked for in the background."""
        server = server or self.server
        if not server:
            self.models, self.models_status = [], "Set the computer first"
            self.on_change()
            return
        where = ollama_url(server).split("://", 1)[-1]
        self.models_status = f"Asking {where}…"
        self.on_change()

        def job():
            try:
                ms = ollama_models(server)
                self.models, self.models_at = ms, server
                self.models_status = (f"{len(ms)} model{'s' if len(ms) != 1 else ''} on {where}" if ms
                                      else f"No models on {where} yet (ollama pull one there)")
            except Exception as ex:
                self.models, self.models_at, self.models_status = [], "", str(ex)[:90]
            self.on_change()
        threading.Thread(target=job, daemon=True, name="friend-models").start()
