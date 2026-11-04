"""setup.sh's Debian non-free change on its own (NON_FREE_AWK), with mawk (Debian's awk) and gawk: non-free goes beside
main in Debian's own entries for this release, one-line (sources.list, as Debian 12's and 13's installers write it) and
deb822 (.sources: apt modernize-sources', a cloud image's mirror+file), with its options, comments and spacing kept;
anyone else's entries (Docker's, Google's, Microsoft's, deb-multimedia's), another release's, a CD's, a turned-off
stanza and ones with non-free already stay as they are. Then debian_non_free itself, in a mount namespace with
/etc/apt of its own and apt-get and apt-cache stood in for: the files it changed, said; apt-get update run again; and
when apt can't read them then, every file back as it was, byte for byte (its permissions too)."""
import os, re, shutil, subprocess, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
ROOT = os.environ.get("PITATO_ROOT", ROOT)
T = SP + "/debsrc"
shutil.rmtree(T, ignore_errors=True)
os.makedirs(T)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


setup = open(ROOT + "/setup.sh").read()
prog = re.search(r"NON_FREE_AWK=\$\(cat <<'AWK'\n(.*?)\nAWK\n\)", setup, re.S).group(1)
open(T + "/non_free.awk", "w").write(prog)
awks = [a for a in ("mawk", "gawk", "original-awk", "busybox") if shutil.which(a)]
check(f"awks to try it with: {awks} (mawk, Debian's own, among them)", "mawk" in awks)


def run_awk(awk, text, code="trixie", deb822=False):
    open(T + "/in", "w").write(text)
    cmd = [awk] + (["awk"] if awk == "busybox" else []) + ["-v", f"code={code}", "-v", f"deb822={int(deb822)}",
                                                          "-f", T + "/non_free.awk", T + "/in"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else f"ERROR {r.returncode}: {r.stderr}"


INSTALLER_13 = """#deb cdrom:[Debian GNU/Linux 13.1.0 _Trixie_ - Official amd64 DVD Binary-1 with firmware 20250906-10:24]/ trixie contrib main non-free-firmware

deb http://deb.debian.org/debian/ trixie main non-free-firmware
deb-src http://deb.debian.org/debian/ trixie main non-free-firmware

deb http://security.debian.org/debian-security trixie-security main non-free-firmware
deb-src http://security.debian.org/debian-security trixie-security main non-free-firmware

# trixie-updates, to get updates before a point release is made;
# see https://www.debian.org/doc/manuals/debian-reference/ch02.en.html#_updates_and_backports
deb http://deb.debian.org/debian/ trixie-updates main non-free-firmware
deb-src http://deb.debian.org/debian/ trixie-updates main non-free-firmware
"""
def turned_on(text):   # (Debian's lines, not the comments)
    return "".join(l if l.startswith("#") else l.replace(" main non-free-firmware", " main non-free non-free-firmware")
                   for l in text.splitlines(True))


INSTALLER_13_ON = turned_on(INSTALLER_13)
INSTALLER_12 = INSTALLER_13.replace("trixie", "bookworm").replace("Trixie", "Bookworm")
MODERNIZED = """# Modernized from /etc/apt/sources.list
Types: deb deb-src
URIs: http://deb.debian.org/debian/
Suites: trixie trixie-updates
Components: main non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

# Modernized from /etc/apt/sources.list
Types: deb deb-src
URIs: http://security.debian.org/debian-security/
Suites: trixie-security
Components: main non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
"""
CLOUD = """Types: deb deb-src
URIs: mirror+file:///etc/apt/mirrors/debian.list
Suites: trixie trixie-updates trixie-backports
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb deb-src
URIs: mirror+file:///etc/apt/mirrors/debian-security.list
Suites: trixie-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg"""          # (no newline at its end)
OTHERS = """deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable
deb [arch=amd64] https://dl.google.com/linux/chrome/deb/ stable main
deb [arch=amd64,arm64,armhf] https://packages.microsoft.com/debian/13/prod trixie main
deb https://www.deb-multimedia.org trixie main non-free
deb http://deb.debian.org/debian/ bookworm main
deb http://deb.debian.org/debian/ trixie main contrib non-free non-free-firmware
deb cdrom:[Debian GNU/Linux 13.1.0 _Trixie_ - Official amd64 DVD Binary-1]/ trixie contrib main non-free-firmware
#deb http://deb.debian.org/debian/ trixie main
"""
KINDS = """deb [ arch=amd64 signed-by=/usr/share/keyrings/debian-archive-keyring.gpg ] http://ftp.us.debian.org/debian trixie main contrib
deb	http://mirror.example.edu/debian/	trixie	main	contrib   # tabs, and a comment: main
  deb http://192.168.1.2:3142/debian trixie-backports main
deb http://deb.debian.org/debian stable main#right after
deb http://deb.debian.org/debian trixie contrib main non-free-firmware
"""
KINDS_ON = """deb [ arch=amd64 signed-by=/usr/share/keyrings/debian-archive-keyring.gpg ] http://ftp.us.debian.org/debian trixie main non-free contrib
deb	http://mirror.example.edu/debian/	trixie	main non-free	contrib   # tabs, and a comment: main
  deb http://192.168.1.2:3142/debian trixie-backports main non-free
deb http://deb.debian.org/debian stable main non-free#right after
deb http://deb.debian.org/debian trixie contrib main non-free non-free-firmware
"""
STANZAS = """# Debian's, written by hand
types: deb
uris: https://deb.debian.org/debian
suites: trixie
components:main contrib
signed-by:
 -----BEGIN PGP PUBLIC KEY BLOCK-----
 .
 mQINBGPL0BUBEAD...
 -----END PGP PUBLIC KEY BLOCK-----

Types: deb
URIs: https://deb.debian.org/debian
Suites: trixie-backports
Components: main
Enabled: no

Types: deb
URIs: https://deb.debian.org/debian
Suites: trixie
Components: non-free
"""
for awk in awks:
    check(f"[{awk}] Debian 13's installer (sources.list): non-free beside main on each of Debian's lines, the CD's "
          "and the comments as they were", run_awk(awk, INSTALLER_13) == INSTALLER_13_ON)
    check(f"[{awk}] ...and run again: nothing more", run_awk(awk, INSTALLER_13_ON) == INSTALLER_13_ON)
    check(f"[{awk}] Debian 12's (bookworm), the same", run_awk(awk, INSTALLER_12, code="bookworm") == turned_on(INSTALLER_12))
    check(f"[{awk}] ...but not for another release (it's on trixie)", run_awk(awk, INSTALLER_12) == INSTALLER_12)
    check(f"[{awk}] deb822 (apt modernize-sources'): Components gets it, in both stanzas",
          run_awk(awk, MODERNIZED, deb822=True)
          == MODERNIZED.replace("Components: main non-free-firmware", "Components: main non-free non-free-firmware"))
    check(f"[{awk}] a cloud image's (mirror+file, backports, no newline at its end)",
          run_awk(awk, CLOUD, deb822=True) == CLOUD.replace("Components: main", "Components: main non-free") + "\n")
    check(f"[{awk}] anyone else's (Docker, Google, Microsoft, deb-multimedia), another release, non-free already, "
          "a CD, a comment: as they were", run_awk(awk, OTHERS) == OTHERS)
    got = run_awk(awk, KINDS)
    check(f"[{awk}] options with blanks, tabs, a comment after, backports from a cache, stable, main not first: "
          "non-free right after main, the rest as it was", got == KINDS_ON)
    if got != KINDS_ON:
        print(got)
    got = run_awk(awk, STANZAS, deb822=True)
    check(f"[{awk}] deb822 by hand: lower-case names, no blank after the colon, a key inside it; a turned-off "
          "stanza, and one without main, left be", got == STANZAS.replace("components:main contrib",
                                                                         "components:main non-free contrib", 1))
    if got != STANZAS.replace("components:main contrib", "components:main non-free contrib", 1):
        print(got)

# ---- debian_non_free itself, with an /etc/apt of its own ----
part = re.search(r"\nos_field\(\) \{.*?\n\}\n", setup, re.S).group(0)
part += re.search(r"\napt_has\(\) \{.*?\ndebian_non_free\(\) \{.*?\n\}\n", setup, re.S).group(0)
open(T + "/part.sh", "w").write(part)
os.makedirs(T + "/bin")
open(T + "/bin/apt-get", "w").write("""#!/bin/bash
# stand-in: notes it; update fails if FAIL_WITH_NONFREE is set and a source has non-free
echo "apt-get $*" >> "$LOG"
if [ "$1" = update ] && [ -n "$FAIL_WITH_NONFREE" ] && grep -rqsE ' non-free( |$)' /etc/apt/sources.list /etc/apt/sources.list.d; then
  echo "E: The repository doesn't have non-free (pretend)"; exit 100
fi
exit 0
""")
os.chmod(T + "/bin/apt-get", 0o755)
open(T + "/inner.sh", "w").write(f"""#!/bin/bash
set -e
mount --make-rprivate /
mount --bind "$APT" /etc/apt
printf 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\\nNAME="Debian GNU/Linux"\\nVERSION_ID="13"\\nVERSION_CODENAME=trixie\\nID=debian\\n' > {T}/os-release
export PITATO_OS_RELEASE={T}/os-release PATH={T}/bin:$PATH
. {T}/part.sh
rc=0; debian_non_free || rc=$?
echo "RC: $rc"
""")


def apt_dir(name, files):
    d = f"{T}/{name}"
    os.makedirs(d + "/sources.list.d")
    for path, (text, mode) in files.items():
        open(f"{d}/{path}", "w").write(text)
        os.chmod(f"{d}/{path}", mode)
    return d


def run_part(d, **env):
    if os.path.exists(T + "/log"):
        os.remove(T + "/log")
    r = subprocess.run(["unshare", "-m", "bash", T + "/inner.sh"], capture_output=True, text=True,
                       env=dict(os.environ, APT=d, LOG=T + "/log", **env))
    log = open(T + "/log").read().splitlines() if os.path.exists(T + "/log") else []
    return r.stdout + r.stderr, log


d = apt_dir("a", {"sources.list": (INSTALLER_13, 0o644), "sources.list.d/docker.list": (OTHERS.splitlines()[0] + "\n", 0o644),
                  "sources.list.d/debian.sources": (MODERNIZED, 0o640), "sources.list.d/notes.txt": ("main\n", 0o644)})
out, log = run_part(d)
check(f"debian_non_free: the files it changed, said ({out.strip()!r})",
      "Non-free is on now in: /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources" in out and "RC: 0" in out)
check("...changed as above, Docker's and the notes left be, permissions kept (0640 stays 0640)",
      open(d + "/sources.list").read() == INSTALLER_13_ON
      and open(d + "/sources.list.d/debian.sources").read().count("main non-free non-free-firmware") == 2
      and open(d + "/sources.list.d/docker.list").read() == OTHERS.splitlines()[0] + "\n"
      and open(d + "/sources.list.d/notes.txt").read() == "main\n"
      and oct(os.stat(d + "/sources.list.d/debian.sources").st_mode & 0o777) == "0o640")
check(f"...apt-get update run again, to read them ({log})", log == ["apt-get update"])
check("...and its copies of them gone from /var/tmp", not [f for f in os.listdir("/var/tmp") if f.startswith("pietato-apt-")])
out, log = run_part(d)
check(f"run again: nothing to change, so it says it couldn't (1) and apt isn't asked ({out.strip()!r}, {log})",
      "RC: 1" in out and log == [] and "Non-free" not in out)

d = apt_dir("b", {"sources.list": (INSTALLER_13, 0o644), "sources.list.d/debian.sources": (MODERNIZED, 0o644)})
before = {p: open(f"{d}/{p}", "rb").read() for p in ("sources.list", "sources.list.d/debian.sources")}
out, log = run_part(d, FAIL_WITH_NONFREE="1")
after = {p: open(f"{d}/{p}", "rb").read() for p in ("sources.list", "sources.list.d/debian.sources")}
check(f"apt can't read them with non-free: every file back as it was, byte for byte, and apt-get update again "
      f"({log}, {out.strip().splitlines()[-1]!r})", before == after and log == ["apt-get update", "apt-get update"]
      and "RC: 1" in out)

d = apt_dir("c", {"sources.list": ("# no sources here\n", 0o644)})
out, log = run_part(d)
check(f"nowhere to put it (no Debian sources): 1, nothing asked of apt ({out.strip()!r})", "RC: 1" in out and log == [])
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
