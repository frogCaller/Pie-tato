"""For the tests: Pietato's names all in one place, as when it was one file (import pietato_all as g). The app is the
pitato package in the Pietato folder (PITATO_ROOT, or the folder above this one); setting a name here sets it in each
of the package's modules that has it, and reloading this reloads the package."""
import importlib
import sys
import types

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = (_os.environ.get("PITATO_REPO") or _os.environ.get("PITATO_ROOT")
         or _os.path.dirname(_HERE))     # (another working copy of it, if one's named)
if _REPO not in sys.path:
    sys.path.append(_REPO)           # (after this folder)

_ORDER = ["theme", "config", "asyou", "util", "lengths", "net", "system", "gpicase", "bluetooth", "screen", "gpu", "radio", "tv", "library", "home",
          "weather", "documents", "filters", "cameras", "nearby", "voice", "listen", "bot", "coder", "crypto", "stocks",
          "homeassistant", "pihole", "plex", "jellyfin", "computers", "sims", "clock", "mandelbrot", "snake", "shrink", "update", "emulator", "discs", "games", "handoff",
          "www", "chromium",
          "inputs", "control",
          "screens.draw",
          "screens.home", "screens.keyboard", "screens.player", "screens.plex", "screens.jellyfin", "screens.photos",
          "screens.reading", "screens.channels", "screens.radio", "screens.finance", "screens.remote", "screens.lights",
          "screens.camera", "screens.bot", "screens.coder", "screens.sims", "screens.snake", "screens.games",
          "screens.settings", "screens.bluetooth", "screens.controller", "screens.weather", "screens.web", "screens.computers", "screens.progs", "screens.pihole", "screens.sysdash",
          "screens.hasettings", "screens.websettings", "screens.www", "screens.chromium", "screens.handoff",
          "screens.attract", "screens.together", "screens.konami",
          "media", "app",
          "assist", "face", "screens.assist"]   # (last: their names never hide another module's, as computers' parse)
_MAYBE = {"screens.hasettings", "screens.websettings", "www", "chromium", "screens.www", "screens.chromium",
          "assist", "face", "screens.assist"}   # (in the newer working copy only, for now)

_reloading = "_mods" in globals()
def _load(n):
    try:
        return importlib.import_module("pitato." + n)
    except ModuleNotFoundError as ex:
        if n in _MAYBE and ex.name == "pitato." + n:
            return None
        raise


_mods = [_m for _m in (_load(_n) for _n in _ORDER) if _m is not None]
if _reloading:                       # importlib.reload(pietato_all): the whole package afresh, as before
    for _m in _mods:
        importlib.reload(_m)
for _m in _mods:                     # (what's asked of the bot, kept for this test alone, not where the Pi keeps it)
    if _m.__name__ == "pitato.assist":
        _m.ASSIST_FILE = _os.path.join(_os.environ.get("PIETATO_TEST_WORK") or "/tmp", "tassist_gk",
                                       f"assist_{_os.getpid()}.json")


class _AllOfIt(types.ModuleType):
    def __getattr__(self, name):
        for m in _mods:
            d = vars(m)
            if name in d:
                return d[name]
        raise AttributeError(f"pitato has no {name!r}")

    def __setattr__(self, name, value):
        hit = False
        if not name.startswith("__"):
            for m in _mods:
                if name in vars(m):
                    setattr(m, name, value)
                    hit = True
        if not hit:
            super().__setattr__(name, value)


sys.modules[__name__].__class__ = _AllOfIt

if _os.environ.get("PITATO_FINE_TEST"):    # (every picture of the menus drawn finely, as on a 4K TV: fine.py)
    _fine = importlib.import_module("pitato.fine")
    _fine.set_scale(int(_os.environ["PITATO_FINE_TEST"]))
    # a test's own pictures (a sheet of screenshots, a look at one) take a fine one as its usual-size copy; the app's
    # code never gets that help, so a fine picture where a plain one should be still fails there
    from PIL import Image as _PILImage, ImageDraw as _PILDraw
    _TESTS = _HERE + _os.sep

    def _from_test():
        return sys._getframe(2).f_code.co_filename.startswith(_TESTS)

    _paste = _PILImage.Image.paste

    def _test_paste(self, im, box=None, mask=None):
        if _from_test():
            im, box, mask = (_fine.plain(x) if isinstance(x, _fine.Fine) else x for x in (im, box, mask))
        return _paste(self, im, box, mask)
    _PILImage.Image.paste = _test_paste
    _draw = _PILDraw.Draw

    def _test_draw(im, mode=None):
        if isinstance(im, _fine.Fine) and sys._getframe(1).f_code.co_filename.startswith(_TESTS):
            return _fine.FineDraw(im, mode)
        return _draw(im, mode)
    _PILDraw.Draw = _test_draw
    from PIL import ImageChops as _PILChops

    def _test_chop(fn):                    # (a test comparing pictures: ImageChops.difference and the rest)
        def chop(*args, **kw):
            if _from_test():
                args = [_fine.plain(x) if isinstance(x, _fine.Fine) else x for x in args]
            return fn(*args, **kw)
        return chop
    for _n in ("difference", "add", "subtract", "multiply", "screen", "lighter", "darker", "invert", "logical_and",
               "logical_or", "logical_xor", "add_modulo", "subtract_modulo", "blend", "composite", "offset"):
        if hasattr(_PILChops, _n):
            setattr(_PILChops, _n, _test_chop(getattr(_PILChops, _n)))
