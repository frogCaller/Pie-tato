# A stand-in for python-evdev where it isn't installed (run.py puts this folder on the path then): its key names
# as numbers, and no devices. Enough for the tests, which make their own controllers.
import collections
class _E:
    def __getattr__(self, n): return hash(n) % 100000
ecodes=_E()
InputDevice=UInput=list_devices=None
AbsInfo = collections.namedtuple("AbsInfo", "value min max fuzz flat resolution")
