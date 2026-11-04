# Tests

Each test runs part of Pietato for real (its screens, its web page, setup.sh) with pretend controllers, screens and
servers around it, and prints `ok` or `FAIL` for each thing it checks. It passes when it ends with `ALL OK`.

Run them as root, as Pietato runs on a Pi (some mount things or start servers of their own):

    sudo python3 tests/run.py                  # the ones GitHub runs
    sudo python3 tests/run.py test_touch       # just one, or a few
    sudo python3 tests/run.py --offline        # with no network but this machine's own, as GitHub runs them
    sudo python3 tests/run.py --all            # every test
    python3 tests/run.py --list                # which is which

Each test gets a folder of its own, with `fixtures` copied in, and its output goes to a log. A failing test's last
lines are shown.

What they need: Python 3.11 or newer with Pillow, numpy, Flask and Playwright (evdev too, or the stand-in in `stub`
is used), the programs in `.github/workflows/tests.yml`, and a user for setup.sh's tests to set up Pietato for:
`sudo useradd -m -G audio gpitest`.

Some tests need more than that: game files and emulators built, voices, servers, or the internet. `--list` says what
each one needs. Put the big files in a folder and point `PIETATO_TEST_ASSETS` at it, and they're linked into each
test's folder.
