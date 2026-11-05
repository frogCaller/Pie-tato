"""What the players and games run as: you, the owner of your home folder, not root. Media mode stays root (the screen,
the buttons, the console), but mplayer and the emulator open what comes from the internet, Plex and Jellyfin, and
files dropped in through the web page, so a bad one there gets no further than you could: your files, the machine's
sound, screen and graphics chip (the audio, video and render groups), and no way up to root through sudo (setpriv's
no new privileges, for them and what they start). What a game writes in (its saves, its emulator's own folder) is
made yours before it starts, as what root made there (an older Pietato's games, a save from another of yours) would
be in its way. What they leave for media mode to read (the AI player's look at the screen, a game's achievements) is
read with care: a plain file, not too big, never a link to something else, or a pipe that would keep it waiting.
Piper and Chromium run as you already (voice.py, chromium.py)."""
import grp
import os
import pwd
import shutil
import stat
import tempfile

from .config import home_dir

AS_YOU = os.environ.get("PITATO_AS_ROOT") != "1"  # (the tests' own folders are root's: tests/paths.py turns it off)
YOUR_GROUPS = ("audio", "video", "render")        # the machine's sound, its screen, its graphics chip
SHM = "/dev/shm"


def as_you(home=None):
    """How a player or a game runs as you: (what goes before its command, Popen's arguments). ([], {}): as root, as
    ever, when Pietato isn't root, or your home folder is root's (no one else to run it as)."""
    if not AS_YOU or os.geteuid() != 0:
        return [], {}
    home = home or home_dir()
    try:
        st = os.stat(home)
    except OSError:
        return [], {}
    if st.st_uid == 0:
        return [], {}
    try:
        u = pwd.getpwuid(st.st_uid)
        name, gid = u.pw_name, u.pw_gid
    except KeyError:                               # (an owner with no name: its number, its folder's group)
        name, gid = str(st.st_uid), st.st_gid
    groups = {gid}
    for g in YOUR_GROUPS:
        try:
            groups.add(grp.getgrnam(g).gr_gid)
        except KeyError:
            pass
    groups.discard(0)
    env = dict(os.environ, HOME=home, USER=name, LOGNAME=name)
    nnp = shutil.which("setpriv")
    return ([nnp, "--no-new-privs", "--"] if nnp else []), {"user": st.st_uid, "group": gid,
                                                             "extra_groups": sorted(groups), "env": env}


def nice_now(proc, nice):
    """One started as you, given the priority it would have given itself as root (only root can raise it)."""
    try:
        os.setpriority(os.PRIO_PROCESS, proc.pid, nice)
    except (OSError, AttributeError, TypeError):
        pass


def hand_over(folder, you):
    """A folder a game writes in (its saves, its emulator's own), and what's in it, yours (you: as_you()'s Popen
    arguments): made if it isn't there, and what root made in it given to you. Links aren't followed."""
    uid, gid = you["user"], you["group"]
    try:
        os.makedirs(folder, exist_ok=True)
        st = os.lstat(folder)
        if stat.S_ISDIR(st.st_mode) and st.st_uid == 0:
            os.chown(folder, uid, gid, follow_symlinks=False)
    except OSError as ex:
        print(f"games: {folder} isn't yours ({ex})", flush=True)
        return
    for root, dirs, files in os.walk(folder):
        for n in dirs + files:
            p = os.path.join(root, n)
            try:
                if os.lstat(p).st_uid == 0:
                    os.chown(p, uid, gid, follow_symlinks=False)
            except OSError:
                pass


def shm_path(name):
    """A file's place where a player or a game can leave it for media mode, whoever it runs as."""
    base = SHM if os.path.isdir(SHM) and os.access(SHM, os.W_OK) else tempfile.gettempdir()
    return os.path.join(base, name)


def read_theirs(path, most=8 << 20):
    """The bytes of a file a player or a game left (as you): a plain file of at most `most`, opened without following
    a link or waiting on a pipe. OSError when it's anything else."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size > most:
            raise OSError(f"not a file to read: {path}")
        data = f.read(most + 1)
    if len(data) > most:
        raise OSError(f"too big to read: {path}")
    return data
