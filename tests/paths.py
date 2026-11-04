"""Where a test works. SP: a folder of its own (PIETATO_TEST_WORK, which run.py makes for each test), with the fixtures
copied in and the big files only some tests need (PIETATO_TEST_ASSETS, a folder of them) linked in. ROOT: the Pietato
folder under test (PITATO_ROOT, or the folder above this one). TESTS: this folder. A test run on its own gets a new
folder in /tmp, set up the same way."""
import os
import shutil
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("PITATO_ROOT") or os.path.dirname(TESTS)
FIXTURES = os.path.join(TESTS, "fixtures")


def make_work(where=None):
    """A folder for one test: the fixtures copied in (a test may change them), the assets linked in. Its path."""
    work = where or tempfile.mkdtemp(prefix="pietato-test-")
    os.makedirs(os.path.join(work, "out"), exist_ok=True)
    for name in sorted(os.listdir(FIXTURES)):
        src, dst = os.path.join(FIXTURES, name), os.path.join(work, name)
        if os.path.lexists(dst):
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)
    assets = os.environ.get("PIETATO_TEST_ASSETS")
    if assets and os.path.isdir(assets):
        for name in sorted(os.listdir(assets)):
            dst = os.path.join(work, name)
            if not os.path.lexists(dst):
                os.symlink(os.path.join(assets, name), dst)
    return work


SP = os.environ.get("PIETATO_TEST_WORK")
if not SP:
    SP = make_work()
    os.environ["PIETATO_TEST_WORK"] = SP
os.environ.setdefault("PITATO_ROOT", ROOT)
