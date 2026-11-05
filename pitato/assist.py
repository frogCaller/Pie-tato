"""The bot as an assistant: what you ask it to do, said or typed, understood here without a model, so it's done at
once (and with no bot computer set up at all): music and the radio, timers and a focus timer, a to-do list, notes
and reminders kept on the Pi, opening an app, the lights, the time. Anything else goes to its model, as ever.
parse() says what was asked (or None); Assist keeps the list, the notes, the reminders and the timers, and says
which have come due. Media mode does the asking (pitato/screens/assist.py)."""
import json
import os
import re
import threading
import time

ASSIST_FILE = "/var/lib/pitato/assist.json"   # the list, notes, reminders and timers (root only, like the conversation)
FOCUS_MINS, BREAK_MINS = 25, 5      # a focus timer, then a break
TASKS_KEPT, NOTES_KEPT, DONE_KEPT = 200, 200, 30   # (the oldest go after this many; ticked-off ones sooner)
LATE_OK = 6 * 3600                  # a reminder missed while the Pi was off: still said, if it's no older than this
PART_HOURS = {"morning": 9, "afternoon": 15, "evening": 18, "night": 20}   # "tomorrow morning": 9 AM

# ---- words: numbers, how long, what time --------------------------------------------------------------------------
ONES = {"zero": 0, "oh": 0, "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90}
FEW = {"couple of": 2, "couple": 2, "few": 3}
UNITS = {"second": 1, "sec": 1, "s": 1, "minute": 60, "min": 60, "m": 60, "hour": 3600, "hr": 3600, "h": 3600}


def numbers(text):
    """Number words as figures: "twenty five minutes" -> "25 minutes", "one hundred" -> "100" ("a" and "an" only
    before a unit of time: "a minute", "an hour")."""
    out, words, i = [], text.split(), 0
    while i < len(words):
        w = words[i]
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w in ("a", "an") and not re.match(r"(?:second|sec|minute|min|hour|hr)s?$", nxt):
            out.append(w)
            i += 1
            continue
        if w in TENS or w in ONES:
            n = TENS.get(w, ONES.get(w, 0))
            i += 1
            if w in TENS and i < len(words) and words[i] in ONES and ONES[words[i]] < 10 \
                    and words[i] not in ("a", "an"):
                n += ONES[words[i]]
                i += 1
            if i < len(words) and words[i] == "hundred":
                n *= 100
                i += 1
                more = lambda w: w in TENS or (w in ONES and w not in ("a", "an", "oh"))  # noqa: E731
                if i + 1 < len(words) and words[i] == "and" and more(words[i + 1]):
                    i += 1
                if i < len(words) and more(words[i]):
                    tens = words[i] in TENS
                    n += TENS.get(words[i], ONES.get(words[i], 0))
                    i += 1
                    if tens and i < len(words) and words[i] in ONES and 0 < ONES[words[i]] < 10 \
                            and words[i] not in ("a", "an"):
                        n += ONES[words[i]]
                        i += 1
            out.append(str(n))
            continue
        out.append(w)
        i += 1
    return " ".join(out)


def duration(text):
    """Seconds in "10 minutes", "an hour and a half", "half an hour", "1.5 hours", "1 hour 20 minutes", "90 sec",
    "a couple of minutes", "5m": None if it isn't just how long."""
    t = " " + str(text or "").strip().lower() + " "
    t = t.replace("half an hour", "30 minutes").replace("half a minute", "30 seconds")
    t = re.sub(r"\b(?:a )?quarter (?:of an )?hour\b", "15 minutes", t)
    t = " " + numbers(t.strip()) + " "
    t = re.sub(r"\b(?:a |an )?couple(?: of)?\b", "2", t)
    t = re.sub(r"\b(?:a )?few\b", "3", t)
    t = re.sub(r"(\d+(?:\.\d+)?) (hours?|hrs?|minutes?|mins?) and (?:a )?half\b",
               lambda m: f"{float(m.group(1)) + 0.5} {m.group(2)}", t)
    unit = r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|[smh])\b"
    total, found = 0.0, False
    for m in re.finditer(unit, t):
        u = m.group(2)
        total += float(m.group(1)) * (1 if u.startswith("s") else 60 if u.startswith("m") else 3600)
        found = True
    rest = re.sub(r"\b(?:and|for|of|about|just|only|exactly|roughly|around|a)\b", " ", re.sub(unit, " ", t))
    if not found or rest.strip():
        return None                                    # (other words in it: not just how long)
    return int(round(total)) if 0 < total <= 24 * 3600 else None


def say_duration(secs):
    """"10 minutes", "1 hour 30 minutes", "45 seconds"."""
    secs = int(round(secs))
    h, m, s = secs // 3600, secs % 3600 // 60, secs % 60
    parts = []
    if h:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    if s and not h:
        parts.append(f"{s} second{'s' if s != 1 else ''}")
    return " ".join(parts) or "0 seconds"


def clock_time(text, now=None):
    """When "at 5", "at 5 pm", "at 5:30", "at five thirty", "at noon", "tomorrow at 9", "tonight at 8", "at 17:00"
    says, from now (the next time it's that time: 5 means 5 pm in the afternoon): seconds since the epoch, or None."""
    now = time.time() if now is None else now
    t = numbers(text.strip().lower())
    t = re.sub(r"\b(\d{1,2}) (\d{2})\b", r"\1:\2", t)           # ("five thirty": 5:30)
    t = re.sub(r"\b(\d{1,2}) o'?clock\b", r"\1", t)
    day = 0
    if re.search(r"\btomorrow\b", t):
        day = 1
        t = re.sub(r"\btomorrow\b", " ", t)
    evening = bool(re.search(r"\b(?:tonight|this evening|in the evening|at night)\b", t))
    morning = bool(re.search(r"\b(?:in the morning|this morning)\b", t))
    afternoon = bool(re.search(r"\b(?:in the afternoon|this afternoon)\b", t))
    t = re.sub(r"\b(?:tonight|this evening|in the evening|at night|in the morning|this morning|in the afternoon|"
               r"this afternoon|today)\b", " ", t)
    m = re.search(r"\b(?:at )?(noon|midday|midnight)\b", t)
    if m:
        hh, mm, half = (0 if m.group(1) == "midnight" else 12), 0, None
    else:
        m = re.search(r"\bat (\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?(?=\s|$)", t)
        if not m:
            return None
        hh, mm = int(m.group(1)), int(m.group(2) or 0)
        half = (m.group(3) or "").replace(".", "") or None
        if hh > 23 or mm > 59 or (half and not 1 <= hh <= 12):
            return None
        if half == "pm" and hh < 12:
            hh += 12
        elif half == "am" and hh == 12:
            hh = 0
        elif half is None and hh <= 12:
            if evening or afternoon:
                hh = hh + 12 if hh < 12 else hh
            elif morning:
                hh = 0 if hh == 12 else hh
    base = time.localtime(now)
    if half is None and not (evening or afternoon or morning) and hh <= 12 and not m.group(0).strip().startswith(
            ("noon", "midday", "midnight", "at noon", "at midday", "at midnight")):
        options = [hh % 12, hh % 12 + 12] if hh != 0 else [0, 12]
    else:
        options = [hh]
    best = None
    for d in range(day, day + 2):
        for h in options:
            when = time.mktime((base.tm_year, base.tm_mon, base.tm_mday + d, h, mm, 0, 0, 0, -1))
            if when > now + 30 and (best is None or when < best) and (day == 0 or d == day):
                best = when
        if best is not None:
            break
    return best


def say_clock(when, now=None, h24=False):
    """"5:30 PM", "tomorrow at 9:00 AM", "Monday at 8:00 PM"."""
    now = time.time() if now is None else now
    t, n = time.localtime(when), time.localtime(now)
    clock = time.strftime("%H:%M", t) if h24 else time.strftime("%I:%M %p", t).lstrip("0")
    days = (time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 12, 0, 0, 0, 0, -1)) -
            time.mktime((n.tm_year, n.tm_mon, n.tm_mday, 12, 0, 0, 0, 0, -1))) / 86400
    if round(days) == 0:
        return clock
    if round(days) == 1:
        return f"tomorrow at {clock}"
    return f"{time.strftime('%A', t)} at {clock}"


# ---- what was asked -----------------------------------------------------------------------------------------------
FILLER = re.compile(r"^(?:(?:hey|hi|hello|ok|okay|please|so|um|uh|er|and|now|then|alright|all right|yo|oh)\s+)+")
POLITE = re.compile(r"^(?:(?:can|could|would|will) you(?: please)?|i want you to|i'd like you to|i need you to|"
                    r"go ahead and|please|i want to|i wanna|i wan na|i'd like to|i would like to|i'd love to|"
                    r"i would love to|let's|lets|let us|let me(?! know)|can i|could i|may i|can we|could we|"
                    r"i'm gonna|im gonna|i am gonna|i'm going to|im going to|i am going to)\s+")
TRAIL = re.compile(r"(?:\s+(?:please|thanks|thank you|for me|now|right now|ok|okay))+$")
LIST = r"(?:(?:my|the|our)\s+)?(?:(?:to ?do|to-do|todo|task|tasks|shopping|grocery|groceries)\s+)?list"


def normal(text, call=()):
    """What was said, plain: lower case, no punctuation but what times need, the please and the hey taken off, and
    what it's called before it ("potato, shut down": call is ("hey potato", "potato"))."""
    t = " ".join(str(text or "").lower().replace("’", "'").split())
    t = re.sub(r"\b([ap])\.? ?m\b\.?", r"\1m", t)             # (5 p.m., 5 p m: 5 pm)
    t = re.sub(r"[\"“”!?¿¡;,]+", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    t = " ".join(t.split())
    for _ in range(3):
        t = FILLER.sub("", t)
        t = POLITE.sub("", t)
        for c in call:
            if c and t.startswith(c + " "):
                t = t[len(c) + 1:]
    return TRAIL.sub("", t).strip()


class Ask:
    """What was asked: kind (play, timer, task_add...), its details, and what was said (plain: normal's)."""
    __slots__ = ("kind", "args", "said")

    def __init__(self, kind, said="", **args):
        self.kind, self.args, self.said = kind, args, said

    def __getitem__(self, k):
        return self.args.get(k)

    def __repr__(self):
        return f"Ask({self.kind!r}, {self.args!r})"


def _rx(*patterns):
    return [re.compile(p + r"$") for p in patterns]


TIMER = _rx(r"(?:set|start|make|create|put on|put)(?: me| up)? (?:a |an |the |my )?(?:(?P<label>[a-z][a-z ]{0,24}?) )?"
            r"timer (?:for |of |to )?(?P<dur>.+?)(?: for (?:the |my )?(?P<label2>[a-z][a-z ]{0,24}))?",
            r"(?:set|start|make|create)(?: me| up)? (?:a |an )?(?P<dur>.+?) timer"
            r"(?: for (?:the |my )?(?P<label2>[a-z][a-z ]{0,24}))?",
            r"(?P<dur>[\da-z. ]+?) timer(?: for (?:the |my )?(?P<label2>[a-z][a-z ]{0,24}))?",
            r"timer (?:for )?(?P<dur>.+)")
TIMER_STOP = _rx(r"(?:cancel|stop|delete|remove|clear|turn off|end|kill|reset)(?: the| my| all(?: the| my)?| all)?"
                 r" (?:(?P<label>[a-z][a-z ]{0,24}?) )?timers?")
TIMER_LEFT = _rx(r"how (?:much time|long)(?: is| has it got| do i have)? left"
                 r"(?: on (?:the |my )?(?:(?P<label>[a-z ]+?) )?timer)?",
                 r"how many (?:minutes|seconds|hours)(?: are| is| do i have)? left"
                 r"(?: on (?:the |my )?(?:[a-z ]+? )?timer)?",
                 r"(?:how(?:'s| is) (?:the |my )?timer(?: doing)?|check (?:the |my )?timers?|time left"
                 r"|what's left on (?:the |my )?timer)")
FOCUS = _rx(r"(?:start|begin|do|let's do|let's start)? ?(?:a |an |the |my )?(?:focus|pomodoro)"
            r"(?: session| mode| timer| time)?"
            r"(?: for (?P<dur>.+))?",
            r"(?:help me |let me |let's |i want to |i need to |time to )?focus(?: for (?P<dur>.+))?")
FOCUS_STOP = _rx(r"(?:stop|end|cancel|quit|finish)(?: the| my)? (?:focus|focusing|pomodoro)(?: session| mode| timer)?",
                 r"stop focusing|i'm done focusing")
BREAK = _rx(r"(?:take|start|have)(?: a| my)?(?: (?P<dur>[\da-z. ]+?))? break", r"break time")
TASK_ADD = _rx(r"(?:add|put|write|stick) (?P<text>.+?) (?:to|on|onto|in|on to) " + LIST,
               r"(?:add|new|create|make)(?: a| another)? (?:task|to ?do|todo|to-do|reminder to)[: ]+(?P<text>.+)",
               r"(?:to ?do|todo|to-do|task)[: ]+(?P<text>.+)")
TASKS = _rx(r"(?:what's|what is|whats|read|show|tell me|list|check|go through|read out)(?: me)?(?: what's)?(?: on)?"
            r" " + LIST,
            r"(?:what's|what is|whats) on " + LIST + r"(?: today)?",
            r"what do i (?:need|have|got) to do(?: today)?",
            r"(?:what are|read|list|show)(?: me)? my (?:tasks|to ?dos|to-dos|todos)(?: for today)?")
TASK_DONE = _rx(r"(?:cross|tick|check|mark) (?P<text>.+?) off(?: (?:of )?" + LIST + r")?",
                r"(?:check off|cross off|tick off|mark off|check|mark|complete|finish|finished)(?: the)? (?P<text>.+?)"
                r"(?: (?:as )?(?:done|complete|completed|finished))?(?: (?:on|from|off) " + LIST + r")?",
                r"(?:i'm done with|i am done with|done with|i did|i've done|i have done|i finished|i completed)"
                r"(?: the)? (?P<text>.+?)(?: (?:on|from) " + LIST + r")?",
                r"(?P<text>.+?) is (?:done|finished|complete)")
TASK_REMOVE = _rx(r"(?:remove|delete|take|erase|scratch) (?P<text>.+?) (?:from|off|off of) " + LIST)
TASKS_CLEAR = _rx(r"(?:clear|empty|delete|erase|wipe)(?: all| everything on| out)? " + LIST,
                  r"clear (?:the |my )?(?:done|finished|completed|ticked off|checked off)(?: tasks| things| items)?")
NOTE_ADD = _rx(r"(?:take|make|write|add|save|jot)(?: down)?(?: a| this)? note(?: that| saying| to say| about)?"
               r"[: ]+(?P<text>.+)",
               r"note(?: that|:| down)? (?P<text>.+)",
               r"write (?:this )?down(?: that)?[: ]+(?P<text>.+)",
               r"remember that (?P<text>.+)",
               r"remember (?P<text>(?:my|the|our|i|i'm|i am|we|it's|its|that's|his|her|their|where) .+)")
REMEMBER_TO = _rx(r"(?:remember|don't let me forget|dont let me forget) to (?P<text>.+)")
NOTES = _rx(r"(?:read|show|what are|what's in|whats in|list|tell me|check)(?: me)?(?: all)? my notes",
            r"what (?:did i|have i)(?: asked you to)? (?:note|write down|ask you to remember|told you to remember)",
            r"(?:my )?notes")
NOTES_CLEAR = _rx(r"(?:clear|delete|erase|wipe|forget)(?: all)?(?: of)?(?: my| the)? notes",
                  r"forget (?:that|the last note|my last note)")
REMIND = _rx(r"remind me (?P<rest>.+)", r"(?:set|make|create|add)(?: me)? (?:a |an )?reminder (?P<rest>.+)")
ALARM = _rx(r"(?:set|make|create|put)(?: me| up)? (?:an |a |the |my )?alarm(?: clock)? (?:for |at |to )?(?P<when>.+)",
            r"wake me(?: up)? (?P<when>(?:at|in|tomorrow|tonight) .+)", r"alarm (?:for |at )?(?P<when>.+)")
ALARM_STOP = _rx(r"(?:cancel|stop|delete|remove|clear|turn off|forget)(?: all)?(?: of)?(?: my| the)? alarms?")
TIMER_HOW = _rx(r"(?:set|start|make|create|put on)(?: me| up)? (?:a |an |the |my )?(?:new |quick )?timer", r"timer")
REMINDERS = _rx(r"(?:what are|read|show|list|tell me|check)(?: me)?(?: all)? my reminders",
                r"(?:what|which) reminders (?:do i have|have i got|are there)(?: today)?", r"(?:my )?reminders")
REMINDERS_STOP = _rx(r"(?:cancel|delete|remove|clear|forget)(?: all)?(?: of)?(?: my| the)? reminders?"
                     r"(?: (?:to|about|for) (?P<text>.+))?")
PAUSE = _rx(r"(?:pause|stop|hold|halt)(?: the| this| that| it| all)?(?: music| song| track| radio| station| playing|"
            r" sound| audio| it| that)?", r"(?:be quiet|shush|hush|silence|shut up)",
            r"(?:turn|switch|shut) off (?:the |this )?(?:music|song|radio|sound)",
            r"(?:turn|switch|shut) (?:the |this )?(?:music|song|radio|sound) off")
RESUME = _rx(r"(?:resume|unpause|continue|keep playing|carry on|play again|start again|keep going)(?: the| it)?"
             r"(?: music| song| track| radio| playing)?", r"play")
NEXT = _rx(r"(?:next|skip)(?: the)?(?: song| track| one| this(?: song| one| track)?| it)?",
           r"play the next (?:song|track|one)",
           r"(?:go to |play )?(?:the )?next (?:song|track)")
PREV = _rx(r"previous(?: song| track| one)?", r"(?:last|go back (?:a|one)) (?:song|track|one)",
           r"play the (?:previous|last) (?:song|track|one)", r"play (?:that|this|it) again")
LOUDER = _rx(r"(?:turn (?:it|this|that|the (?:volume|music|sound)) up|louder|volume up"
             r"|turn up(?: the)? (?:volume|music|sound)|"
             r"(?:raise|increase|up)(?: the)? (?:volume|sound)|(?:make it )?louder)")
QUIETER = _rx(r"(?:turn (?:it|this|that|the (?:volume|music|sound)) down|quieter|softer|volume down|turn down(?: the)? "
              r"(?:volume|music|sound)|(?:lower|decrease|reduce)(?: the)? (?:volume|sound)"
              r"|(?:make it )?(?:quieter|softer))")
VOLUME = _rx(r"(?:set |turn |put )?(?:the )?volume (?:to |at |on )?(?P<n>\d{1,3})(?: percent| %|%)?",
             r"(?:set|turn|put) (?:it|the music|the sound) (?:to |at )(?P<n>\d{1,3})(?: percent| %|%)?")
MUTE = _rx(r"(?P<un>un)?mute(?: the| it)?(?: sound| music| volume| it)?")
SHUFFLE = _rx(r"(?:turn )?(?:shuffle|mix it up)(?: (?:on|off|it|the songs|the music))?", r"turn (?:on|off) shuffle")
PLAY_ALL = _rx(r"shuffle (?:all )?(?:of )?(?:my |all my |the |some )?(?:music|songs|tunes)")
PLAYING = _rx(r"(?:what's|what is|whats) (?:playing|this song|that song|the song|this track|on)(?: now)?",
              r"what (?:song|track|station) is (?:this|playing|on)(?: now)?", r"who (?:is this|sings this|is singing)")
PLAY = _rx(r"(?:play|put on|start playing|listen to|hear|i want to (?:hear|listen to)|let's (?:hear|listen to)|"
           r"let me hear|"
           r"queue up|throw on|spin)(?: me| us)?(?: some| a little| a bit of)? (?P<what>.+)")
OPEN = _rx(r"(?:open|show(?: me)?|go to|launch|start|switch to|take me to|bring up|pull up|go back to|browse|"
           r"look at|look through|go through|view|see|check out)(?: the| my| up| all my| all the)?"
           r" (?P<app>.+?)(?: app| tab| page| screen)?")
HOME = _rx(r"(?:go |take me |back to the |go back )?home(?: screen)?", r"go back home")
LIGHTS = _rx(r"(?:turn|switch|put|flip) (?P<onoff>on|off) (?:the |all the |all |my )?(?P<which>[a-z ]*?)"
             r"(?:lights?|lamps?)",
             r"(?:turn|switch|put|flip) (?:the |all the |all |my )?(?P<which>[a-z ]*?)(?:lights?|lamps?)"
             r" (?P<onoff>on|off)",
             r"(?:the |all the |my )?(?P<which>[a-z ]*?)(?:lights?|lamps?) (?P<onoff>on|off)",
             r"(?P<onoff>lights out)")
TIME = _rx(r"(?:what(?:'s| is) the time|what time is it|whats the time|time|what time it is|the time)"
           r"(?: now| right now)?")
DATE = _rx(r"(?:what(?:'s| is) (?:the date|today's date|todays date|the day)|what day is (?:it|today)|what's today|"
           r"whats the date|what date is it)(?: today)?")
WEATHER = _rx(r"(?:what's|what is|whats|how's|how is|hows) the weather(?: like)?(?: now| today| outside| right now)?",
              r"weather", r"(?:check|look at|tell me|give me|read me)(?: the)? weather(?: forecast)?(?: for today)?")
HELP = _rx(r"what can (?:you|i ask you to) do", r"what (?:can|could) i (?:ask|say)(?: you)?", r"help")
# a game, something to watch, being bored, the Pi itself, the camera; and yes or no, to a question it asked
GAME = _rx(r"(?:let's |let us |i want to |i'd like to |can we |can i |wanna )?play (?:a |an |some |another |any )?"
           r"(?:random |video )?games?(?: of (?P<name>.+))?",
           r"(?:start|open|launch|pick|choose|find)(?: me| us)? (?:a |an |some |another |any )?(?:random |video )?game"
           r"(?: of (?P<name>.+))?",
           r"play (?:the |a )?game (?:called |named )?(?P<name>.+)", r"play (?P<name>.+?) (?:the )?game")
WATCH_WHAT = (r"(?:tv|the tv|television|some tv|a channel|any channel|a tv channel|channels|a show|some shows|"
              r"something|something to watch|a cartoon|cartoons|some cartoons|toons|a movie|movies|some movies|"
              r"a film|films|some films|an old movie|an old film|a classic film|the news|news|some news|sports|"
              r"some sports)")
WATCH = _rx(r"(?:i want to |i'd like to |let's |let us |can we |can i |could we )?watch "
            r"(?!(?:out|it|this|that|me|us|them|him|her|yourself|your|over|for|as|how|what|where|who)\b)(?P<what>.+)",
            r"(?:put on|turn on|switch on|show me|play|start|find me|pick|choose)(?: me| us)? (?:something on )?"
            r"(?P<what>" + WATCH_WHAT + r")",
            r"(?:put|turn|switch) (?P<what>(?:the )?(?:news|tv|cartoons|sports|a channel)) on")
CHANNEL_NEXT = _rx(r"(?:next|change the|change|switch the|switch|another|a different|other|new) channel", r"channel up")
CHANNEL_PREV = _rx(r"(?:previous|last|go back a|back a|the last) channel", r"channel down")
BORED = _rx(r"(?:i'm|im|i am|i feel|i'm feeling|feeling|so|i'm so|i am so|i'm getting|getting|kinda|kind of)? ?bored"
            r"(?: now| right now| out of my mind| stiff)?",
            r"what (?:should|can|could) (?:i|we) do(?: now| today)?", r"entertain me", r"there's nothing to do",
            r"nothing to do", r"i(?:'m| am) bored what (?:should|can) i do")
COOL_WORD = r"(?: really| very| super)? (?:cool|neat|awesome|amazing|interesting|trippy|fun|pretty|fancy|wild|random)"
COOL = _rx(r"(?:show|give|find|pick)(?: me| us)? (?:something|anything|some thing)" + COOL_WORD +
           r"(?: to (?:look at|see|watch))?(?: on (?:the|your|my) screen)?",
           r"(?:do|draw|put on)(?: me| us)? something" + COOL_WORD, r"(?:something|anything)" + COOL_WORD)
UPDATE = _rx(r"(?:update|upgrade)(?: yourself| itself| your software| the software| pietato| potato| everything)?"
             r"(?: now)?",
             r"(?:check for|look for|get|install|are there any|is there an?|any|get the|install the|do the|do an?) "
             r"(?:new )?(?:updates?|new version|newest version)(?: now)?")
SHUTDOWN = _rx(r"(?:shut ?down|shut yourself down|shut down the pi|power off|power down|switch off|turn off|"
               r"turn yourself off|turn the pi off|turn off the pi|switch yourself off|shut off)(?: now)?")
REBOOT = _rx(r"(?:restart|reboot)(?: yourself| the pi| your pi| the computer)?(?: now)?",
             r"(?:restart|reboot) (?P<app>media mode|pietato|potato|the app)(?: now)?")
CAM_WAYS = (r"left|right|clockwise|counterclockwise|anticlockwise|counter clockwise|anti clockwise|upside down|"
            r"around|back")
CAM_TURN = _rx(r"(?:rotate|turn|flip) (?:the |my )?(?P<which>[a-z ]*?)camera(?:'s)? (?:picture|image|view)"
               r"(?: (?P<way>" + CAM_WAYS + r"))?",
               r"rotate (?:the |my )?(?P<which>[a-z ]*?)camera(?: (?P<way>" + CAM_WAYS + r"))?",
               r"flip (?:the |my )?(?P<which>[a-z ]*?)camera(?: (?P<way>upside down|over|around))?")
CAM_STEER = _rx(r"(?:turn|move|point|pan|tilt|swing|aim) (?:the |my )?(?P<which>[a-z ]*?)camera (?:to the )?"
                r"(?P<way>left|right|up|down)", r"(?:look|pan|tilt) (?P<way>left|right|up|down)",
                r"camera (?P<way>left|right|up|down)")
PHOTO_WORD = r"(?:photo|picture|pic|shot|image|snap|selfie)"
PHOTOS_WORD = r"(?:photos|pictures|pics|images|shots|snaps|camera roll|photo album|gallery)"
SHOW_WORD = r"(?:show|open|see|view|bring up|pull up|look at|browse|go through|look through|find)(?: me)?"
PHOTO_LAST = _rx(SHOW_WORD + r" (?:my |the )?(?:last|latest|newest|most recent) " + PHOTO_WORD +
                 r"(?: (?:i|you|we) took| taken| (?:i|you) just took)?",
                 r"(?:my |the )?(?:last|latest|newest|most recent) " + PHOTO_WORD + r"(?: (?:i|you|we) took)?",
                 r"what(?:'s| is| was) the (?:last|latest|newest) " + PHOTO_WORD + r" (?:i|you|we) took")
PHOTOS_WHEN = _rx(SHOW_WORD + r" (?:my |the |all my |all the |all of my )?" + PHOTOS_WORD +
                  r" (?:from|of|taken|i took|you took)(?: on)? (?P<when>today|yesterday|this week)",
                  r"(?:my |the )?" + PHOTOS_WORD +
                  r" (?:from|taken|i took)(?: on)? (?P<when>today|yesterday|this week)")
SLIDESHOW = _rx(r"(?:start|play|show|begin|do|run|put on)(?: me)?(?: a| the| my)? slide ?show"
                r"(?: of (?:my |the |all my )?" + PHOTOS_WORD + r")?",
                r"slide ?show(?: of (?:my |the )?" + PHOTOS_WORD + r")?",
                r"(?:show|play) (?:my |the |all my )?" + PHOTOS_WORD + r" (?:as a|in a) slide ?show")
PHOTO_NEXT = _rx(r"(?:go to |show me |show )?(?:the )?next " + PHOTO_WORD)
PHOTO_PREV = _rx(r"(?:go (?:back )?to |show me |show )?(?:the )?previous " + PHOTO_WORD,
                 r"go back (?:a|one) " + PHOTO_WORD)
# a game by its name, said as an app would be ("start shrek 2", "launch tetris"): the assistant looks for it
LAUNCH = _rx(r"(?:start|launch|open|run|boot up|load up|fire up|load|boot)(?: up)?(?: the)?(?: game)? (?P<name>.+)")
YES = _rx(r"(?:yes|yeah|yea|yep|yup|sure|ok|okay|do it|go ahead|please do|let's do it|sounds good|go for it|alright|"
          r"all right|yes do it|of course|absolutely|why not)(?: then)?")
NO = _rx(r"(?:no|nope|nah|not now|not|no thanks|no thank you|cancel|never mind|nevermind|don't|forget it|maybe later)"
         r"(?: then)?")


def _first(rules, t):
    for r in rules:
        m = r.match(t)
        if m:
            return m
    return None


def remind_parts(rest, now=None):
    """(when, what) from what follows "remind me": "at 5 to call mom", "to call mom at 5", "in 20 minutes to take the
    pizza out", "tomorrow at 9 about the bank". when is None for one with no time in it (a thing to do, then)."""
    now = time.time() if now is None else now
    r = " " + rest.lower() + " "
    r = r.replace("half an hour", "30 minutes").replace(" an hour and a half", " 90 minutes")
    r = " " + numbers(r.strip()) + " "
    r = re.sub(r"\b(?:a )?few minutes\b", "3 minutes", r)
    r = re.sub(r"\b(?:a )?couple(?: of)? minutes\b", "2 minutes", r)
    when, span = None, None
    m = re.search(r"\bin ((?:\d+(?:\.\d+)? ?(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)(?: and )?)+)", r)
    if m and duration(m.group(1)):
        when, span = now + duration(m.group(1)), m.span()
    else:
        day = r"(?:tomorrow|tonight|this morning|this afternoon|this evening)"
        part = r"(?:in the morning|in the afternoon|in the evening|tomorrow|tonight|this morning|this afternoon|" \
               r"this evening)"
        clock = r"(?:noon|midday|midnight|\d{1,2}(?:[: ]\d{2})?(?: ?[ap]m)?(?: o'?clock)?)"
        for m in re.finditer(rf"\b(?:{day} )?(?:at |@ ?){clock}(?: {part})?|\b(?:{day} )?(?:noon|midday|midnight)"
                             rf"(?: {part})?|\b(?:{day} )?\d{{1,2}}(?::\d{{2}})? ?[ap]m(?: {part})?", r):
            phrase = m.group(0).replace("@", "at ")
            if not re.search(r"\bat\b", phrase):
                phrase = re.sub(rf"^({day} )?", lambda x: (x.group(1) or "") + "at ", phrase)
            got = clock_time(phrase, now)
            if got is not None:
                when, span = got, m.span()
                break
    if when is None:                                   # no clock time: "tomorrow morning", "tonight", "tomorrow"
        m = re.search(r"\b(?:(tomorrow) (morning|afternoon|evening|night)|(tonight)|(?:this|in the) "
                      r"(morning|afternoon|evening)|(tomorrow))\b", r)
        if m:
            tomorrow = bool(m.group(1) or m.group(5))
            h = PART_HOURS["night" if m.group(3) else m.group(2) or m.group(4) or "morning"]
            when = clock_time(f"{'tomorrow ' if tomorrow else ''}at {h % 12 or 12} {'am' if h < 12 else 'pm'}", now)
            span = m.span() if when is not None else None
    what = r if span is None else r[:span[0]] + " " + r[span[1]:]
    what = " ".join(what.split())
    what = re.sub(r"^(?:for )?(?:to|that|about|of|i need to|i have to|i've got to|i should)\s+", "", what)
    what = re.sub(r"\s+(?:to|that|about|for)$", "", what).strip()
    return when, what


APPS = {   # what you might call each app: its name in the library
    "home screen": "Home", "tv": "TV", "television": "TV", "telly": "TV", "music": "Music", "songs": "Music",
    "radio": "Radio", "camera": "Camera", "cameras": "Camera", "photos": "Photos", "pictures": "Photos",
    "pics": "Photos", "gallery": "Photos", "camera roll": "Photos", "photo album": "Photos", "photo albums": "Photos",
    "photo gallery": "Photos", "photo library": "Photos", "images": "Photos", "videos": "Videos", "movies": "Videos",
    "films": "Videos",
    "games": "Games", "weather": "Weather", "forecast": "Weather", "finance": "Finance", "stocks": "Finance",
    "crypto": "Finance", "markets": "Finance", "bot": "Bot", "chat": "Bot", "apps": "Apps",
    "simulator": "Apps", "sims": "Apps", "files": "Files", "documents": "Files", "system": "System", "settings": "Settings",
    "plex": "Plex", "jellyfin": "Jellyfin", "cartoons": "Cartoons", "free movies": "Free Movies", "news": "News",
    "sports": "Sports", "streams": "Streams", "tv remote": "TV Remote", "remote": "TV Remote", "lights": "Lights",
    "pi-hole": "Pi-hole", "pihole": "Pi-hole", "pi hole": "Pi-hole", "web": "Web", "browser": "Web",
    "internet": "Web", "snake": "Snake", "clock": "Clock", "the clock": "Clock", "time": "Clock",
    "rock paper scissors": "Rock Paper Scissors", "game of life": "Game of Life", "life": "Game of Life",
    "forest fire": "Forest Fire", "mandelbrot": "Mandelbrot Set", "mandelbrot set": "Mandelbrot Set",
    "konami code": "Konami code", "konami codes": "Konami code", "konami": "Konami code",
    "today": "Today", "to do list": "Today", "my list": "Today", "list": "Today", "tasks": "Today",
    "notes": "Today", "reminders": "Today", "timer": "Today", "timers": "Today",
}


def app_named(words):
    """The app those words name ("the weather", "my photos", "pi hole"), or None."""
    w = re.sub(r"^(?:the|my|our)\s+", "", words.strip())
    w = re.sub(r"\s+(?:app|tab|page|screen)$", "", w)
    return APPS.get(w)


def parse(text, now=None, call=()):
    """What was asked, if it's something done here: an Ask, or None (it goes to the model). call: what it's called
    (its wake phrase, and its name: "hey potato", "potato"), taken off before what's asked, or after it ("shut down,
    potato") when that's something done here."""
    t = normal(text, call)
    ask = parse_plain(t, now)
    if ask is None:
        c = next((c for c in call if c and t.endswith(" " + c)), None)
        if c:
            ask = parse_plain(normal(t[:-len(c) - 1]), now)
    return ask


def parse_plain(t, now=None):
    """parse's work, on what was said made plain (normal's)."""
    if not t or len(t) > 160:
        return None
    if _first(YES, t):
        return Ask("yes", t)
    if _first(NO, t):
        return Ask("no", t)
    if _first(BORED, t):
        return Ask("bored", t)
    if _first(COOL, t):
        return Ask("cool", t)
    if _first(WEATHER, t):
        return Ask("weather", t)
    if _first(UPDATE, t):
        return Ask("update", t)
    if _first(SHUTDOWN, t):
        return Ask("shutdown", t)
    m = _first(REBOOT, t)
    if m:
        return Ask("reboot", t, app=bool(m.groupdict().get("app")))
    m = _first(TIMER_STOP, t)
    if m:
        return Ask("timer_stop", t, label=(m.group("label") or "").strip())
    m = _first(TIMER_LEFT, t)
    if m:
        return Ask("timer_left", t)
    m = _first(FOCUS_STOP, t)
    if m:
        return Ask("focus_stop", t)
    m = _first(BREAK, t)
    if m:
        secs = duration(m.group("dur")) if m.groupdict().get("dur") else BREAK_MINS * 60
        if secs:
            return Ask("break", t, secs=secs)
    m = _first(FOCUS, t)
    if m:
        secs = duration(m.group("dur")) if m.groupdict().get("dur") else FOCUS_MINS * 60
        if secs:
            return Ask("focus", t, secs=secs)
    m = _first(TIMER, t)
    if m:
        secs = duration(m.group("dur"))
        label = (m.groupdict().get("label") or m.groupdict().get("label2") or "").strip()
        label = "" if label in ("new", "another", "quick", "little", "kitchen") else label
        if secs:
            return Ask("timer", t, secs=secs, label=label)
    if _first(TIMER_HOW, t):
        return Ask("timer_how", t)
    if _first(ALARM_STOP, t):
        return Ask("alarm_stop", t)
    m = _first(ALARM, t)
    if m:
        when = m.group("when").strip()
        if not re.match(r"(?:at|in|tomorrow|tonight|this) ", when):
            when = "at " + when
        if t.startswith("wake") and re.search(r"\bat \d{1,2}(?::\d{2}| \d{2})?$", when):
            when += " am"                              # ("wake me up at 7": in the morning)
        at, rest = remind_parts(when, now)
        if at is not None and len(rest.split()) <= 2:
            return Ask("alarm", t, at=at)
    m = _first(REMINDERS_STOP, t)
    if m:
        return Ask("reminders_stop", t, text=(m.group("text") or "").strip())
    m = _first(REMINDERS, t)
    if m:
        return Ask("reminders", t)
    m = _first(REMIND, t)
    if m:
        when, what = remind_parts(m.group("rest"), now)
        if what:
            return Ask("remind", t, at=when, text=what) if when else Ask("task_add", t, text=what)
    m = _first(TASKS_CLEAR, t)
    if m:
        return Ask("tasks_clear", t, done_only=bool(re.search(r"done|finished|completed|ticked|checked", t)))
    m = _first(TASKS, t)
    if m:
        return Ask("tasks", t)
    m = _first(TASK_REMOVE, t)
    if m:
        return Ask("task_remove", t, text=m.group("text").strip())
    m = _first(TASK_ADD, t)
    if m:
        return Ask("task_add", t, text=m.group("text").strip())
    m = _first(TASK_DONE, t)
    if m:
        return Ask("task_done", t, text=m.group("text").strip())
    m = _first(REMEMBER_TO, t)
    if m:
        return Ask("task_add", t, text=m.group("text").strip())
    m = _first(NOTES_CLEAR, t)
    if m:
        return Ask("notes_clear", t, last_only=t.startswith("forget") and "notes" not in t)
    m = _first(NOTES, t)
    if m:
        return Ask("notes", t)
    m = _first(NOTE_ADD, t)
    if m and len(m.group("text").split()) >= 2:
        return Ask("note_add", t, text=m.group("text").strip())
    m = _first(LIGHTS, t)
    if m:
        on = m.group("onoff") == "on"
        which = (m.groupdict().get("which") or "").strip()
        return Ask("lights", t, on=on, which=re.sub(r"^(?:the|all the|all|my)\s+", "", which))
    m = _first(CAM_TURN, t)
    if m:
        way = m.group("way") or ""
        step = 180 if way in ("upside down", "around", "over") else -90 if way in (
            "left", "counterclockwise", "anticlockwise", "counter clockwise", "anti clockwise") else 90
        if way == "back":
            step = 0
        return Ask("cam_turn", t, step=step, which=(m.group("which") or "").strip())
    m = _first(CAM_STEER, t)
    if m:
        return Ask("cam_steer", t, way=m.group("way"), which=(m.groupdict().get("which") or "").strip())
    if _first(SLIDESHOW, t):
        return Ask("photo", t, which="slideshow")
    m = _first(PHOTOS_WHEN, t)
    if m:
        return Ask("photo", t, which="when", when=m.group("when"))
    if _first(PHOTO_LAST, t):
        return Ask("photo", t, which="last")
    if _first(PHOTO_NEXT, t):
        return Ask("next", t, photo=True)
    if _first(PHOTO_PREV, t):
        return Ask("previous", t, photo=True)
    if _first(CHANNEL_NEXT, t):
        return Ask("next", t, channel=True)
    if _first(CHANNEL_PREV, t):
        return Ask("previous", t, channel=True)
    m = _first(GAME, t)
    if m:
        name = (m.groupdict().get("name") or "").strip()
        if app_named(name) == "Snake":
            return Ask("open", t, app="Snake")
        return Ask("game", t, name=name)
    m = _first(WATCH, t)
    if m:
        what = re.sub(r"^(?:some|a|an|the)\s+", "", m.group("what").strip())
        if app_named(what) not in (None, "TV", "News", "Cartoons", "Sports", "Free Movies", "Videos"):
            return Ask("open", t, app=app_named(what))    # ("watch the camera": the Camera tab)
        return Ask("watch", t, what=what)
    if _first(PLAY_ALL, t):
        return Ask("play", t, what="my music")
    for kind, rules in (("time", TIME), ("date", DATE), ("weather", WEATHER), ("help", HELP),
                        ("playing", PLAYING), ("next", NEXT), ("previous", PREV), ("louder", LOUDER),
                        ("quieter", QUIETER), ("shuffle", SHUFFLE), ("home", HOME)):
        if _first(rules, t):
            return Ask(kind, t)
    m = _first(VOLUME, t)
    if m:
        return Ask("volume", t, pct=max(0, min(100, int(m.group("n")))))
    m = _first(MUTE, t)
    if m:
        return Ask("unmute" if m.group("un") else "mute", t)
    if _first(PAUSE, t):
        return Ask("pause", t)
    if _first(RESUME, t):
        return Ask("resume", t)
    m = _first(OPEN, t)
    if m and app_named(m.group("app")):
        return Ask("open", t, app=app_named(m.group("app")))
    m = _first(PLAY, t)
    if m:
        what = m.group("what").strip()
        if app_named(what) in ("Snake",):
            return Ask("open", t, app="Snake")
        return Ask("play", t, what=what)
    return None


# ---- what's kept ----------------------------------------------------------------------------------------------------
def words_of(text):
    return [w for w in re.findall(r"[a-z0-9']+", str(text).lower())
            if w not in ("the", "a", "an", "my", "to", "some", "of", "for", "and")]


def best_match(items, text, key=lambda x: x["text"]):
    """The item whose words are most like text's (most of them in it), or None."""
    want = set(words_of(text))
    if not want:
        return None
    best, score = None, 0.0
    for it in items:
        have = set(words_of(key(it)))
        if not have:
            continue
        common = len(want & have)
        s = common / max(len(want), 1) + common / max(len(have), 1)
        if common and s > score:
            best, score = it, s
    return best if score >= 0.9 else None


def say_list(items):
    """"milk", "milk and eggs", "milk, eggs and bread"."""
    items = [str(x) for x in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class Assist:
    """Your list, notes, reminders and timers, kept on the Pi (ASSIST_FILE), and which of them have come due."""

    def __init__(self, path=None):
        self.path = path or ASSIST_FILE
        self.tasks, self.notes, self.reminders, self.timers = [], [], [], []
        self.focus_done = {}            # "2026-10-31" -> focus sessions finished that day
        self.lock = threading.Lock()
        self.load()

    def load(self):
        try:
            with open(self.path) as f:
                got = json.load(f)
        except (OSError, ValueError):
            got = {}
        got = got if isinstance(got, dict) else {}

        def rows(name, *keys):
            return [x for x in got.get(name) or [] if isinstance(x, dict) and all(k in x for k in keys)]
        self.tasks = rows("tasks", "text")[-TASKS_KEPT:]
        self.notes = rows("notes", "text")[-NOTES_KEPT:]
        self.reminders = rows("reminders", "text", "at")
        self.timers = rows("timers", "until", "secs")
        self.focus_done = {k: v for k, v in (got.get("focus_done") or {}).items() if isinstance(v, int)}

    def save(self):
        with self.lock:
            data = {"tasks": self.tasks, "notes": self.notes, "reminders": self.reminders, "timers": self.timers,
                    "focus_done": dict(list(self.focus_done.items())[-14:])}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)
        except OSError as ex:
            print(f"couldn't keep the list and the reminders: {ex}", flush=True)

    # the list
    def open_tasks(self):
        return [x for x in self.tasks if not x.get("done")]

    def add_task(self, text):
        text = text.strip().rstrip(".")[:120]
        text = text[:1].upper() + text[1:]
        if any(x["text"].lower() == text.lower() and not x.get("done") for x in self.tasks):
            return False
        self.tasks.append({"text": text, "t": time.time()})
        done = [x for x in self.tasks if x.get("done")]
        if len(done) > DONE_KEPT:
            self.tasks.remove(done[0])
        self.tasks = self.tasks[-TASKS_KEPT:]
        self.save()
        return True

    def tick_task(self, it, done=True):
        it["done"] = bool(done)
        it["done_t"] = time.time() if done else None
        self.save()

    def drop_task(self, it):
        if it in self.tasks:
            self.tasks.remove(it)
            self.save()

    def clear_tasks(self, done_only=False):
        n = len([x for x in self.tasks if x.get("done")]) if done_only else len(self.open_tasks())
        self.tasks = [x for x in self.tasks if not x.get("done")] if done_only else []
        self.save()
        return n

    # notes
    def add_note(self, text):
        text = text.strip()[:300]
        self.notes.append({"text": text[:1].upper() + text[1:], "t": time.time()})
        self.notes = self.notes[-NOTES_KEPT:]
        self.save()

    def clear_notes(self, last_only=False):
        n = 1 if last_only and self.notes else len(self.notes)
        self.notes = self.notes[:-1] if last_only else []
        self.save()
        return n

    # reminders
    def add_reminder(self, at, text, alarm=False):
        text = text.strip()[:160]
        it = {"text": text, "at": float(at), "t": time.time()}
        if alarm:
            it["alarm"] = True
        self.reminders.append(it)
        self.reminders.sort(key=lambda r: r["at"])
        self.save()

    def drop_alarms(self):
        gone = [r for r in self.reminders if r.get("alarm")]
        self.reminders = [r for r in self.reminders if not r.get("alarm")]
        self.save()
        return gone

    def drop_reminders(self, text=""):
        if text:
            r = best_match(self.reminders, text)
            gone = [r] if r else []
        else:
            gone = list(self.reminders)
        self.reminders = [x for x in self.reminders if x not in gone]
        self.save()
        return gone

    # timers: a timer of yours, or the focus timer and its break
    def add_timer(self, secs, label="", kind="timer"):
        now = time.time()
        if kind != "timer":
            self.timers = [x for x in self.timers if x.get("kind", "timer") == "timer"]
        self.timers.append({"until": now + secs, "secs": int(secs), "label": label.strip()[:40], "kind": kind})
        self.timers.sort(key=lambda x: x["until"])
        self.save()

    def own_timers(self):
        return [x for x in self.timers if x.get("kind", "timer") == "timer"]

    def focus(self):
        """The focus timer or its break, running: its timer, or None."""
        return next((x for x in self.timers if x.get("kind") in ("focus", "break")), None)

    def drop_timers(self, label="", kinds=("timer",)):
        mine = [x for x in self.timers if x.get("kind", "timer") in kinds]
        if label and len(mine) > 1:
            hit = best_match(mine, label, key=lambda x: x.get("label") or "")
            mine = [hit] if hit else []
        self.timers = [x for x in self.timers if x not in mine]
        self.save()
        return mine

    def focus_count(self, now=None):
        return self.focus_done.get(time.strftime("%Y-%m-%d", time.localtime(now)), 0)

    def due(self, now=None):
        """What's come due since last asked: [("timer", it)], [("reminder", it)], ("focus", it), ("break", it); each
        said once, and gone (a focus timer's break starts as it ends)."""
        now = time.time() if now is None else now
        out = []
        with self.lock:
            for x in [x for x in self.timers if x["until"] <= now]:
                self.timers.remove(x)
                kind = x.get("kind", "timer")
                out.append((kind, x))
                if kind == "focus":
                    day = time.strftime("%Y-%m-%d", time.localtime(now))
                    self.focus_done[day] = self.focus_done.get(day, 0) + 1
                    self.timers.append({"until": now + BREAK_MINS * 60, "secs": BREAK_MINS * 60, "label": "",
                                        "kind": "break"})
            for r in [r for r in self.reminders if r["at"] <= now]:
                self.reminders.remove(r)
                if now - r["at"] <= LATE_OK:
                    out.append(("reminder", r))
        if out:
            self.save()
        return out

    def next_due(self):
        """When the next timer or reminder comes due (seconds since the epoch), or None."""
        times = [x["until"] for x in self.timers] + [r["at"] for r in self.reminders]
        return min(times) if times else None

    def facts(self, now=None, h24=False):
        """Lines for the bot's model: what's on your list, your reminders and timers, your notes."""
        now = time.time() if now is None else now
        lines = []
        todo = [x["text"] for x in self.open_tasks()]
        if todo:
            lines.append("Their to-do list: " + "; ".join(todo[:12]))
        if self.reminders:
            lines.append("Their reminders: " + "; ".join(f"{r['text']} ({say_clock(r['at'], now, h24)})"
                                                         for r in self.reminders[:8]))
        for x in self.timers:
            what = {"focus": "A focus timer", "break": "A break"}.get(x.get("kind"), "A timer" + (
                f" for {x['label']}" if x.get("label") else ""))
            lines.append(f"{what} is running: {say_duration(max(0, x['until'] - now))} left")
        if self.notes:
            lines.append("Notes they asked you to keep: " + "; ".join(x["text"] for x in self.notes[-10:]))
        if self.focus_count(now):
            lines.append(f"Focus sessions done today: {self.focus_count(now)}")
        return lines
