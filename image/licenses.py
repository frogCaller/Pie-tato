#!/usr/bin/env python3
"""The licences that go with each release's SD card images, in one zip, in their folders as they are here:
THIRD-PARTY-LICENSES.md, LICENSE, the licenses folder, the fonts' licence and the console pictures' credits.
GitHub runs it for each release (.github/workflows/image.yml).

    python3 image/licenses.py OUT.zip
"""
import os
import sys
import zipfile

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = ("THIRD-PARTY-LICENSES.md", "LICENSE", "licenses", "static/fonts/OFL.txt", "pitato/icons/consoles/CREDITS.txt")


def files():
    """Each file that goes in, as its path here (from the Pietato folder)."""
    for part in PARTS:
        path = os.path.join(TOP, part)
        if os.path.isdir(path):
            for root, dirs, names in os.walk(path):
                dirs.sort()
                for name in sorted(names):
                    yield os.path.relpath(os.path.join(root, name), TOP)
        elif os.path.isfile(path):
            yield part
        else:
            raise SystemExit(f"{part} isn't here")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 image/licenses.py OUT.zip")
    with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files():
            z.write(os.path.join(TOP, rel), rel)
    print(f"{sys.argv[1]}: the licences")


if __name__ == "__main__":
    main()
