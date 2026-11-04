"""The weather starting over (a new place picked, Find me) while a fetch for the same place is on its way, after it
has stored what it got: before, what it got was wiped and nothing fetched again (no weather until the next hour);
now it's fetched again."""
import os, shutil, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, os.environ.get("PITATO_ROOT", ROOT))
S = SP + "/tweatherrace"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S)
import pitato.weather as W
W.CACHE_DIR = S + "/cache"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=5):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return bool(cond())


hold, held = threading.Event(), threading.Event()
fetched = []


def fake_json(url, *a, **k):
    fetched.append(url)
    if "open-meteo" in url:
        return {"current": {"time": "2026-10-22T10:30", "temperature_2m": 71.0, "weather_code": 2, "is_day": 1},
                "hourly": {"time": []}, "daily": {"time": []}}
    if "points" in url:                                # (the first fetch waits here, its weather stored already)
        if not hold.is_set():
            held.set()
            hold.wait(5)
        return {"properties": {"forecast": "https://api.weather.gov/gridpoints/X/1,1/forecast"}}
    if "gridpoints" in url:
        return {"properties": {"periods": [{"name": "Tonight", "detailedForecast": "Clear."}]}}
    raise OSError("offline")


W.fetch_json = fake_json
loc = {"name": "Here", "country": "US", "lat": 45.5, "lon": -122.6}
w = W.Weather(lambda: loc, lambda: "F")
w.refresh(force=True)
check("a fetch on its way, what it got stored already", until(lambda: held.is_set()) and w.data and w.busy)
w.reset()                                              # (the same place picked again: Settings, Find me)
check("...the weather starts over meanwhile: wiped, the fetch still on its way", w.data is None and w.busy)
hold.set()
back = until(lambda: w.data is not None and not w.busy)
asked = sum("open-meteo" in u for u in fetched)
check(f"...then the fetch ends: the weather's fetched again, and here ({asked} asked, "
      f"temp {w.data and w.data.get('temp')})", back and asked == 2 and w.data["temp"] == 71.0)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
