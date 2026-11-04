"""For the tests: the settings files (static/ on a Pi) in the stand-in home folder, where the
tests have always put them."""
import os


def use_home(g, home):
    g.STATIC = home
    for t in g.LIBRARY:
        if t.get("files"):
            t["files"] = [os.path.join(home, os.path.basename(f)) for f in t["files"]]
