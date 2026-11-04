"""The bot as an assistant, its own part (pitato/assist.py): what's asked understood, said or typed, the way Vosk
hears it too (words for numbers, no capitals, no commas); what isn't for it left for the model; how long and what
time; your list, notes, reminders and timers kept, and said once as they come due (a focus timer's break after it,
a reminder missed while the Pi was off still said if it isn't old); and the lines the model's told."""
import json, os, shutil, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, ROOT)
from pitato import assist as A

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


NOW = time.mktime((2026, 10, 31, 13, 32, 0, 0, 0, -1))    # a Saturday, 1:32 PM
T = time.localtime


def at(h, m=0, day=0):
    return time.mktime((2026, 10, 31 + day, h, m, 0, 0, 0, -1))


# ---- how long, what time -------------------------------------------------------------------------------------------
for said, secs in (("10 minutes", 600), ("ten minutes", 600), ("twenty five minutes", 1500), ("an hour", 3600),
                   ("an hour and a half", 5400), ("half an hour", 1800), ("1.5 hours", 5400), ("90 seconds", 90),
                   ("1 hour 20 minutes", 4800), ("a couple of minutes", 120), ("a few minutes", 180), ("5m", 300),
                   ("one hundred and twenty seconds", 120), ("a minute", 60), ("5 min", 300)):
    check(f"how long: {said!r} is {secs} s ({A.duration(said)})", A.duration(said) == secs)
for said in ("the pasta", "", "10", "25 hours", "ten minutes of fun"):
    check(f"...{said!r} isn't how long ({A.duration(said)})", A.duration(said) is None)
check("said back: 1 hour 30 minutes, 45 seconds", A.say_duration(5400) == "1 hour 30 minutes" and A.say_duration(45) == "45 seconds")
for said, want in (("at 5", at(17)), ("at 5 pm", at(17)), ("at 5:30", at(17, 30)), ("at five thirty", at(17, 30)),
                   ("at noon", at(12, day=1)), ("at midnight", at(0, day=1)), ("tomorrow at 9", at(9, day=1)),
                   ("tonight at 8", at(20)), ("at 9 am", at(9, day=1)), ("at 17:00", at(17)), ("at 1", at(13, day=1) if False else at(1, day=1))):
    got = A.clock_time(said, NOW)
    check(f"what time: {said!r} at 1:32 PM is {time.strftime('%a %H:%M', T(want))} "
          f"({time.strftime('%a %H:%M', T(got)) if got else None})", got == want)
check("...said back: 5:00 PM, tomorrow at 9:00 AM, Monday at 8:00 PM",
      A.say_clock(at(17), NOW) == "5:00 PM" and A.say_clock(at(9, day=1), NOW) == "tomorrow at 9:00 AM"
      and A.say_clock(at(20, day=2), NOW) == "Monday at 8:00 PM" and A.say_clock(at(17), NOW, h24=True) == "17:00")

# ---- what's asked ----------------------------------------------------------------------------------------------------
CASES = [
    ("set a timer for ten minutes", "timer", {"secs": 600, "label": ""}),
    ("Hey, can you please set a timer for 3 minutes? Thanks", "timer", {"secs": 180, "label": ""}),
    ("timer 5 min", "timer", {"secs": 300}),
    ("set a pasta timer for an hour and a half", "timer", {"secs": 5400, "label": "pasta"}),
    ("ten minute timer for the eggs", "timer", {"secs": 600, "label": "eggs"}),
    ("cancel the timer", "timer_stop", {"label": ""}),
    ("stop the pasta timer", "timer_stop", {"label": "pasta"}),
    ("how long is left on the timer", "timer_left", {}),
    ("start a focus session", "focus", {"secs": 1500}),
    ("focus for 50 minutes", "focus", {"secs": 3000}),
    ("pomodoro", "focus", {"secs": 1500}),
    ("stop focusing", "focus_stop", {}),
    ("take a break", "break", {"secs": 300}),
    ("take a ten minute break", "break", {"secs": 600}),
    ("add milk to my list", "task_add", {"text": "milk"}),
    ("put eggs on the shopping list", "task_add", {"text": "eggs"}),
    ("add call the bank to my to do list", "task_add", {"text": "call the bank"}),
    ("remind me to buy 2 eggs", "task_add", {"text": "buy 2 eggs"}),
    ("remember to water the plants", "task_add", {"text": "water the plants"}),
    ("what's on my list", "tasks", {}),
    ("what do I need to do today", "tasks", {}),
    ("check off milk", "task_done", {"text": "milk"}),
    ("I did the laundry", "task_done", {"text": "laundry"}),
    ("remove eggs from my list", "task_remove", {"text": "eggs"}),
    ("clear my list", "tasks_clear", {"done_only": False}),
    ("take a note the car is on level 3", "note_add", {"text": "the car is on level 3"}),
    ("remember that the wifi password is cheese", "note_add", {"text": "the wifi password is cheese"}),
    ("read my notes", "notes", {}),
    ("forget that", "notes_clear", {"last_only": True}),
    ("remind me at 5 to call mom", "remind", {"at": at(17), "text": "call mom"}),
    ("remind me to call mom at 5:30 pm", "remind", {"at": at(17, 30), "text": "call mom"}),
    ("remind me in 20 minutes to take the pizza out", "remind", {"at": NOW + 1200, "text": "take the pizza out"}),
    ("remind me tomorrow at 9 about the bank", "remind", {"at": at(9, day=1), "text": "the bank"}),
    ("set a reminder for 5 p.m. to water the plants", "remind", {"at": at(17), "text": "water the plants"}),
    ("remind me to call dad at five thirty", "remind", {"at": at(17, 30), "text": "call dad"}),
    ("remind me at 5 p m to stretch", "remind", {"at": at(17), "text": "stretch"}),
    ("what are my reminders", "reminders", {}),
    ("cancel my reminders", "reminders_stop", {"text": ""}),
    ("play some jazz", "play", {"what": "jazz"}),
    ("play the radio", "play", {"what": "the radio"}),
    ("put on some miles davis", "play", {"what": "miles davis"}),
    ("pause", "pause", {}), ("stop", "pause", {}), ("resume", "resume", {}), ("play", "resume", {}),
    ("next song", "next", {}), ("skip", "next", {}), ("previous song", "previous", {}),
    ("louder", "louder", {}), ("turn it down", "quieter", {}), ("set the volume to 40", "volume", {"pct": 40}),
    ("mute", "mute", {}), ("what's playing", "playing", {}),
    ("open the weather", "open", {"app": "Weather"}), ("show me my photos", "open", {"app": "Photos"}),
    ("open the clock", "open", {"app": "Clock"}), ("start snake", "open", {"app": "Snake"}),
    ("show my list", "tasks", {}), ("go home", "home", {}),
    ("turn off the lights", "lights", {"on": False, "which": ""}),
    ("turn on the kitchen light", "lights", {"on": True, "which": "kitchen"}),
    ("turn the living room lights off", "lights", {"on": False, "which": "living room"}),
    ("lights out", "lights", {"on": False}),
    ("what time is it", "time", {}), ("what day is it", "date", {}), ("what's the weather like", "weather", {}),
    ("what can you do", "help", {}),
    ("set an alarm for 7 am", "alarm", {"at": at(7, day=1)}), ("wake me up at 7", "alarm", {"at": at(7, day=1)}),
    ("set an alarm for 7", "alarm", {"at": at(19)}), ("wake me up tomorrow at 6:30", "alarm", {"at": at(6, 30, day=1)}),
    ("set an alarm for tomorrow morning", "alarm", {"at": at(9, day=1)}), ("cancel my alarm", "alarm_stop", {}),
    ("how many minutes are left", "timer_left", {}), ("shuffle my music", "play", {"what": "my music"}),
    ("remind me to take out the trash tomorrow morning", "remind", {"at": at(9, day=1), "text": "take out the trash"}),
    ("remind me tonight to call mom", "remind", {"at": at(20), "text": "call mom"}),
    ("remind me tomorrow to call the bank", "remind", {"at": at(9, day=1), "text": "call the bank"}),
    ("set a timer", "timer_how", {}), ("cross milk off my list", "task_done", {"text": "milk"}),
    ("tick off milk", "task_done", {"text": "milk"}),
    # bored, a game, something to watch, the Pi itself, the camera; yes or no to a question of its own
    ("I'm bored", "bored", {}), ("im bored", "bored", {}), ("what should I do", "bored", {}),
    ("entertain me", "bored", {}),
    ("show me something cool", "cool", {}), ("can you show me something really cool", "cool", {}),
    ("show us something neat", "cool", {}), ("something cool", "cool", {}), ("do something cool", "cool", {}),
    ("show me something fun to look at", "cool", {}), ("show me something", "watch", {"what": "something"}),
    ("show me something to watch", "watch", {"what": "something to watch"}),
    ("play a game", "game", {"name": ""}), ("let's play a game", "game", {"name": ""}),
    ("play a random game", "game", {"name": ""}), ("play a game of tetris", "game", {"name": "tetris"}),
    ("play the game called sonic", "game", {"name": "sonic"}), ("play mario kart the game", "game",
                                                                {"name": "mario kart"}),
    ("play mario", "play", {"what": "mario"}),
    ("turn on a channel", "watch", {"what": "channel"}), ("watch tv", "watch", {"what": "tv"}),
    ("turn on the tv", "watch", {"what": "tv"}), ("put on some cartoons", "watch", {"what": "cartoons"}),
    ("watch a movie", "watch", {"what": "movie"}), ("watch the news", "watch", {"what": "news"}),
    ("put on sports", "watch", {"what": "sports"}), ("watch popeye", "watch", {"what": "popeye"}),
    ("next channel", "next", {"channel": True}), ("change the channel", "next", {"channel": True}),
    ("previous channel", "previous", {"channel": True}), ("channel up", "next", {"channel": True}),
    ("check for updates", "update", {}), ("update yourself", "update", {}), ("is there an update", "update", {}),
    ("shut down", "shutdown", {}), ("turn off", "shutdown", {}), ("power off", "shutdown", {}),
    ("restart", "reboot", {"app": False}), ("reboot the pi", "reboot", {"app": False}),
    ("restart media mode", "reboot", {"app": True}),
    ("rotate the camera", "cam_turn", {"step": 90, "which": ""}),
    ("rotate the camera left", "cam_turn", {"step": -90}), ("flip the camera upside down", "cam_turn", {"step": 180}),
    ("rotate the camera back", "cam_turn", {"step": 0}), ("rotate the porch camera", "cam_turn", {"which": "porch"}),
    ("turn the camera left", "cam_steer", {"way": "left", "which": ""}), ("look up", "cam_steer", {"way": "up"}),
    ("pan the garage camera right", "cam_steer", {"way": "right", "which": "garage"}),
    ("yes", "yes", {}), ("yes please", "yes", {}), ("okay", "yes", {}), ("sure", "yes", {}), ("go ahead", "yes", {}),
    ("no", "no", {}), ("nah", "no", {}), ("not now", "no", {}), ("no thanks", "no", {}),
    ("check the weather", "weather", {}), ("turn off the music", "pause", {}), ("turn the radio off", "pause", {}),
    ("shut up", "pause", {}),
    # asked your own way, and your photos
    ("I want to play shrek two", "play", {"what": "shrek two"}), ("I wanna play the game shrek two", "game",
                                                                  {"name": "shrek two"}),
    ("I want to play the game schreck to", "game", {"name": "schreck to"}), ("can I add milk to my list", "task_add",
                                                                             {"text": "milk"}),
    ("i want to hear some jazz", "play", {"what": "jazz"}), ("let's watch cartoons", "watch", {"what": "cartoons"}),
    ("i'm going to play tetris", "play", {"what": "tetris"}),
    ("browse my camera roll", "open", {"app": "Photos"}), ("show me my camera roll", "open", {"app": "Photos"}),
    ("look at my pictures", "open", {"app": "Photos"}),
    ("show me my last photo", "photo", {"which": "last"}), ("show me the latest picture I took", "photo",
                                                            {"which": "last"}),
    ("start a slideshow", "photo", {"which": "slideshow"}), ("show my photos from today", "photo",
                                                             {"which": "when", "when": "today"}),
    ("next picture", "next", {"photo": True}), ("previous photo", "previous", {"photo": True}),
]
for said, kind, args in CASES:
    got = A.parse(said, NOW)
    ok = got is not None and got.kind == kind and all(got.args.get(k) == v for k, v in args.items())
    check(f"{said!r}: {kind} {args if args else ''} ({got})", ok)
CALL = ("hey potato", "potato")
for said, kind in (("potato, shut down", "shutdown"), ("hey potato shut down", "shutdown"),
                   ("shut down, potato", "shutdown"), ("Potato, I'm bored!", "bored"), ("potato restart", "reboot"),
                   ("yes potato", "yes"), ("potato, play a game", "game"),
                   ("Hey potato, show me something cool!", "cool")):
    got = A.parse(said, NOW, call=CALL)
    check(f"said to it by name: {said!r} is {kind} ({got})", got is not None and got.kind == kind)
for said in ("potato", "potato salad recipe", "tell me about potatoes"):
    check(f"...{said!r}: for the model", A.parse(said, NOW, call=CALL) is None)
for said in ("tell me a joke", "what do you think about jazz", "I love jazz music", "how are you", "go back",
             "open the pod bay doors", "remember when we went to the beach", "what's the capital of France",
             "take a picture", "what do you see", "hold on", "focus on my homework", "who are you", "",
             "what is this?", "set an alarm for the kids to wake up", "what's a good timer app",
             "turn off the tv", "restart the song", "update my list", "reboot the router", "what's new",
             "the camera is broken", "is this a good game", "watch out", "sure thing", "let me know what you think",
             "start shrek 2", "see you later", "can we talk", "what's something cool about space",
             "that's something cool", "i saw something cool today"):
    got = A.parse(said, NOW)
    check(f"{said!r}: for the model ({got})", got is None)

# ---- what's kept ---------------------------------------------------------------------------------------------------
S = SP + "/tassist"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S)
P = S + "/assist.json"
k = A.Assist(P)
check("a new one: nothing kept", not (k.tasks or k.notes or k.reminders or k.timers))
check("the list: added, once", k.add_task("milk") and k.add_task("call the bank") and not k.add_task("Milk"))
check("...kept with a capital", [x["text"] for x in k.open_tasks()] == ["Milk", "Call the bank"])
check("...found by its words", A.best_match(k.open_tasks(), "the bank") is k.tasks[1]
      and A.best_match(k.open_tasks(), "eggs") is None)
k.tick_task(k.tasks[0])
check("...ticked off", [x["text"] for x in k.open_tasks()] == ["Call the bank"] and k.tasks[0]["done"])
k.add_note("the car is on level 3")
R = time.time()                                       # (from here on: now, as it is)
k.add_reminder(R + 600, "call mom")
k.add_reminder(R + 60, "take the pizza out")
k.add_timer(300, "pasta")
k.add_timer(1500, kind="focus")
check("reminders in order, timers too", [r["text"] for r in k.reminders] == ["take the pizza out", "call mom"]
      and k.timers[0]["label"] == "pasta" and k.focus()["kind"] == "focus")
k2 = A.Assist(P)
check("...all of it kept on the card, only for root", [x["text"] for x in k2.tasks] == ["Milk", "Call the bank"]
      and k2.notes[0]["text"] == "The car is on level 3" and len(k2.reminders) == 2 and len(k2.timers) == 2
      and oct(os.stat(P).st_mode & 0o777) == "0o600")
check("...a broken file: nothing, no trouble", (open(P + "x", "w").write("{not json"), A.Assist(P + "x").tasks)[1] == [])
lines = k.facts(R)
check(f"what the model's told: the list, the reminders, the timers, the notes ({lines})",
      any("Call the bank" in x for x in lines) and any("take the pizza out" in x for x in lines)
      and any("pasta" in x for x in lines) and any("focus timer" in x.lower() for x in lines)
      and any("level 3" in x for x in lines))
check("nothing due yet", k.due(R + 30) == [])
got = k.due(R + 400)
check(f"...the pizza and the pasta, then ({[(a, b.get('text') or b.get('label')) for a, b in got]})",
      sorted(a for a, _ in got) == ["reminder", "timer"])
check("...said once", k.due(R + 400) == [])
got = k.due(R + 1600)
check(f"the focus timer: done, a break starting, counted ({[a for a, _ in got]}, {k.focus_count(R + 1600)})",
      ("focus" in [a for a, _ in got]) and k.focus() and k.focus()["kind"] == "break" and k.focus_count(R + 1600) == 1)
check("...the break, after it", [a for a, _ in k.due(R + 1600 + 301)] == ["break"] and k.focus() is None)
k.add_reminder(R + 1901 - 3600, "missed but recent")
k.add_reminder(R + 1901 - 8 * 3600, "long gone")
got = k.due(R + 1901)
check(f"missed while the Pi was off: said if it's recent, not if it's old ({[b['text'] for _, b in got]})",
      [b["text"] for _, b in got] == ["missed but recent"] and not k.reminders)
check("dropping: a timer by its name, the reminders", (k.add_timer(60, "tea"), k.add_timer(90, "eggs"),
                                                      [x["label"] for x in k.drop_timers("tea")])[2] == ["tea"]
      and [x["label"] for x in k.own_timers()] == ["eggs"])
check("clearing the list: the done ones only, or all", (k.add_task("x"), k.clear_tasks(True))[1] == 1
      and len(k.open_tasks()) == 2 and k.clear_tasks() == 2 and not k.tasks)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
