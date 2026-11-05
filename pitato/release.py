"""Pietato's latest release (where its SD card images are): the one GitHub calls the latest for the Pietato folder's
repository (not a pre-release or a draft), or, when GitHub's API doesn't answer (or it isn't on GitHub), the newest
version among its tags (v1.10 after v1.9; not v1.3-beta). System > Update software followed it before; it follows
main now (update.py), and doesn't ask it. Python's own modules only, so it can run by itself:

    git ls-remote --tags --refs origin | python3 -I release.py OWNER/NAME     (prints the tag, or nothing)
"""
import json
import os
import re
import sys
import urllib.request

API = "https://api.github.com/repos/{repo}/releases/latest"   # (PITATO_RELEASES_API in its place: the tests' own)
AGENT = "Pietato-update"
TIMEOUT = 20
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")           # GitHub's owner/name
TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}")          # a tag git and the shell take as it is
VERSION = re.compile(r"v?(\d{1,9}(?:\.\d{1,9}){0,5})")        # a release's tag: v1.2, 1.10, v2.0.1


def good_tag(tag):
    return (isinstance(tag, str) and bool(TAG.fullmatch(tag)) and ".." not in tag
            and not tag.endswith((".", ".lock")))


def from_github(repo, timeout=TIMEOUT):
    """GitHub's latest release of repo (owner/name): its tag, or None (no answer, none yet, not one of GitHub's)."""
    if not repo or not REPO.fullmatch(repo):
        return None
    url = (os.environ.get("PITATO_RELEASES_API") or API).format(repo=repo)
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            got = json.loads(r.read(500_000).decode("utf-8", "replace"))
    except (OSError, ValueError):                  # (no answer, an error's, a slow one, or not JSON)
        return None
    if not isinstance(got, dict) or got.get("draft") or got.get("prerelease"):
        return None
    tag = got.get("tag_name")
    return tag if good_tag(tag) else None


def newest(tags):
    """The newest version among tags (git ls-remote's lines, or just their names), or None when none is one."""
    best = None
    for line in tags:
        name = str(line).strip().rsplit("refs/tags/", 1)[-1]
        m = VERSION.fullmatch(name)
        if m and good_tag(name):
            key = tuple(int(x) for x in m.group(1).split("."))
            if best is None or key > best[0]:
                best = (key, name)
    return best[1] if best else None


def latest(repo, tags=(), timeout=TIMEOUT):
    """The release to follow: GitHub's latest, else the newest version among tags."""
    return from_github(repo, timeout) or newest(tags)


if __name__ == "__main__":
    print(latest(sys.argv[1] if len(sys.argv) > 1 else "", [] if sys.stdin.isatty() else sys.stdin) or "")
