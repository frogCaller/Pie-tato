"""Your other computers' files, found by their address: a Windows PC's shared folders (a Mac's or a NAS's work
the same way), or a Linux computer's files over SSH (a Mac's too, with Remote Login on). They open read-only, as
folders on this Pi, so nothing on the other computer is changed from here. setup.sh installs what it takes:
smbclient and cifs-utils for shared folders (and samba-common-bin, to find a PC by its own name), sshfs for SSH."""
import contextlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading

COMPUTERS_FILE = "/var/lib/pitato/computers.json"  # the computers added: address, how, user name and password
KNOWN_HOSTS = "/var/lib/pitato/known_hosts"         # SSH computers' keys, kept from the first time (a new one's refused)
NET_ROOT = "/run/pitato/computers"                  # where they open: <address>/<shared folder>, or <address>/ (SSH)
SECRETS = "/run/pitato"                             # a user name and password on their way to a command (root's only)
SMB_PORT, SSH_PORT = 445, 22
LOOK_WAIT = 3.0       # seconds a computer has to answer
OPEN_WAIT = 45        # ...and to open its folders
NEEDS_SETUP = "Run setup.sh on this Pi again: it adds what opening other computers' files takes"
HOST_NAME = re.compile(r"^[A-Za-z0-9_]([A-Za-z0-9_-]*[A-Za-z0-9_])?(\.[A-Za-z0-9_]([A-Za-z0-9_-]*[A-Za-z0-9_])?)*$")


class Trouble(Exception):
    """Why a computer's files didn't open: kind ("login": it wants a user name and password; "bad_login",
    "unknown", "unreachable", "nothing", "noshares", "noshare", "keys", "hostkey", "account", "missing",
    "typo", "gone", "failed") and what to say."""

    def __init__(self, kind, text):
        super().__init__(text)
        self.kind, self.text = kind, text


# ---- what was typed ---------------------------------------------------------------------------
def is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def parse(text):
    """An address as typed: 192.168.1.20, pc.local, \\\\pc\\Media, smb://pc/Media, ssh://me@pc:2222 or me@pc.
    {"host", "port" (0: the usual one), "how" ("smb", "ssh", or "" to find out), "user", "share"}."""
    t = (text or "").strip().replace("\\", "/")
    how = ""
    m = re.match(r"(?i)(smb|cifs|ssh|sftp)://", t)
    if m:
        how = "ssh" if m.group(1).lower() in ("ssh", "sftp") else "smb"
        t = t[m.end():]
    t = t.lstrip("/")
    hostport, _, rest = t.partition("/")
    user = ""
    if "@" in hostport:
        user, _, hostport = hostport.rpartition("@")
        how = how or "ssh"
    host, port = hostport.strip(), 0
    if host.startswith("[") and "]" in host:
        end = host.index("]")
        host, tail = host[1:end], host[end + 1:]
        if tail.startswith(":") and tail[1:].isdigit():
            port = int(tail[1:])
    elif host.count(":") == 1:
        h, _, p = host.partition(":")
        if p.isdigit():
            host, port = h, int(p)
    host = host.rstrip(".")
    if not host or not (is_ip(host) or HOST_NAME.match(host)) or not 0 <= port < 65536:
        raise Trouble("typo", f"“{(text or '').strip()[:40]}” isn't an address. Type it like 192.168.1.20")
    if port and not how:
        how = "smb" if port in (SMB_PORT, 139) else "ssh"
    share = rest.strip("/").split("/")[0] if rest.strip("/") else ""
    return {"host": host, "port": port, "how": how, "user": user.strip(), "share": share}


def address(host, port=0):
    """How a computer is shown and known: 192.168.1.20, pc.local, pc:2222."""
    h = f"[{host}]" if ":" in host else host
    return f"{h}:{port}" if port else h


def folder_name(addr):
    """Its folder under NET_ROOT."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", addr).strip("._") or "computer"


SSH_USER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.@-]*$")   # (never "-..."; no spaces, commas or colons)


def check_login(how, user, password=""):
    """A user name and password that can go to the commands that sign in: or Trouble."""
    if any(ch in (user or "") + (password or "") for ch in "\r\n\0"):
        raise Trouble("typo", "A user name or password can't have a line break in it")
    if how == "ssh" and user and not SSH_USER.match(user):
        raise Trouble("typo", "That user name can't be used for SSH (letters, numbers, . _ - and @ only)")


def share_dir(share):
    """A shared folder's own folder here (a computer can't name one "..")."""
    name = share.replace("/", "_").replace("\\", "_").replace("\0", "")
    return "_" + name if name in ("", ".", "..") else name


def split_user(user):
    """'PC\\me' -> ('me', 'PC'); 'me' or 'me@outlook.com' -> (it, '')."""
    if "\\" in user:
        domain, _, name = user.partition("\\")
        return name, domain
    return user, ""


# ---- asking the computer ---------------------------------------------------------------------
def run_cmd(cmd, timeout=OPEN_WAIT, stdin=None):
    """A command's (return code, what it said). Never raises."""
    try:
        r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as ex:
        return 127, str(ex)


def lookup(host):
    try:
        found = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return None
    found.sort(key=lambda f: f[0] != socket.AF_INET)
    return found[0][4][0] if found else None


def windows_name(host):
    """A Windows PC's own name (DESKTOP-1A2B3C), asked of the network the way Windows does: its address or None."""
    if not shutil.which("nmblookup"):
        return None
    code, said = run_cmd(["nmblookup", host], timeout=8)
    m = re.search(r"^(\d+\.\d+\.\d+\.\d+) " + re.escape(host) + r"<00>", said, re.I | re.M)
    return m.group(1) if m else None


def find_host(host):
    """Its address (an IPv4 one when it has one): by its name, its name.local, or its Windows name. Or Trouble."""
    if is_ip(host):
        return host
    found = lookup(host) or ("." not in host and (lookup(host + ".local") or windows_name(host)))
    if not found:
        raise Trouble("unknown", f"There's no computer called {host} on this network")
    return found


def answers(host, port, wait=LOOK_WAIT):
    """'open', 'closed' (it's there, but nothing listens) or 'silent'."""
    try:
        with socket.create_connection((host, port), timeout=wait):
            return "open"
    except ConnectionRefusedError:
        return "closed"
    except OSError:
        return "silent"


def look(host, ports):
    """Each port at once: {port: 'open' | 'closed' | 'silent'}."""
    out = {}
    threads = [threading.Thread(target=lambda p=p: out.__setitem__(p, answers(host, p)), daemon=True)
               for p in ports]
    for t in threads:
        t.start()
    for t in threads:
        t.join(LOOK_WAIT + 1)
    return {p: out.get(p, "silent") for p in ports}


@contextlib.contextmanager
def secret_file(pairs):
    """A user name and password in a file only root can read, for as long as a command needs it."""
    os.makedirs(SECRETS, mode=0o755, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".login-", dir=SECRETS)
    try:
        with os.fdopen(fd, "w") as f:
            f.write("".join(f"{k}={v}\n" for k, v in pairs if v))
        yield path
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def alive(where):
    """An opened folder that still answers (one whose connection dropped says so straight away)."""
    try:
        os.stat(where)
        return True
    except OSError:
        return False


def mounted(root):
    """The folders opened under root, from the kernel's own list (asks no computer anything)."""
    out = set()
    try:
        with open("/proc/self/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) > 1:
                    p = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), parts[1])
                    if p.startswith(root + "/"):
                        out.add(p)
    except OSError:
        pass
    return out


# ---- shared folders (Windows, a Mac, a NAS) ------------------------------------------------------
def smb_trouble(c, said, signed_in):
    addr = c["addr"]
    if any(s in said for s in ("NT_STATUS_LOGON_FAILURE", "NT_STATUS_WRONG_PASSWORD", "NT_STATUS_NO_SUCH_USER",
                               "NT_STATUS_ACCESS_DENIED", "error(13)")):
        if signed_in:
            return Trouble("bad_login", "That user name or password didn't work")
        return Trouble("login", f"{addr} wants a user name and password")
    if "NT_STATUS_ACCOUNT_RESTRICTION" in said:
        return Trouble("account", "Windows lets an account in from another computer only if it has a password")
    if any(s in said for s in ("NT_STATUS_ACCOUNT_DISABLED", "NT_STATUS_ACCOUNT_LOCKED_OUT",
                               "NT_STATUS_PASSWORD_EXPIRED", "NT_STATUS_PASSWORD_MUST_CHANGE")):
        return Trouble("account", "That account can't sign in right now")
    if "NT_STATUS_BAD_NETWORK_NAME" in said or "error(2)" in said:
        return Trouble("noshare", f"That folder isn't shared on {addr} any more")
    if any(s in said for s in ("NT_STATUS_CONNECTION_REFUSED", "NT_STATUS_HOST_UNREACHABLE", "NT_STATUS_IO_TIMEOUT",
                               "NT_STATUS_NETWORK_UNREACHABLE", "NT_STATUS_UNSUCCESSFUL", "NT_STATUS_CONNECTION_RESET",
                               "NT_STATUS_CONNECTION_DISCONNECTED", "error(111)", "error(112)", "error(113)",
                               "error(110)", "error(115)", "timed out")):
        return Trouble("unreachable", f"{addr} isn't answering. Is it on, and on this network?")
    if any(s in said for s in ("error(19)", "unknown filesystem type", "helper program", "No such file or directory: 'mount")):
        return Trouble("missing", NEEDS_SETUP)
    code = re.search(r"NT_STATUS_\w+|error\(\d+\)", said)
    return Trouble("failed", f"Couldn't open {addr}'s files ({code.group(0) if code else said.strip()[-60:]})")


def smb_login(c):
    user, domain = split_user(c.get("user") or "")
    return [("username", user), ("password", c.get("password") or ""), ("domain", domain)]


def smb_shares(c):
    """The computer's shared folders, not Windows' own (C$, ADMIN$...): [name], or Trouble."""
    if not shutil.which("smbclient"):
        raise Trouble("missing", NEEDS_SETUP)
    cmd = ["smbclient", "-g", "-L", "//" + find_host(c["host"])] + (["-p", str(c["port"])] if c.get("port") else [])
    if c.get("user"):
        with secret_file(smb_login(c)) as login:
            code, said = run_cmd(cmd + ["-A", login])
    else:
        code, said = run_cmd(cmd + ["-N"])
    shares = []
    for line in said.splitlines():
        parts = line.split("|")
        if (len(parts) >= 2 and parts[0] == "Disk" and parts[1] and not parts[1].endswith("$")
                and parts[1] not in (".", "..") and not any(ch in parts[1] for ch in "/\\\0\r\n")):
            shares.append(parts[1])
    if code == 0 or shares:
        return sorted(set(shares), key=str.lower)
    raise smb_trouble(c, said, bool(c.get("user")))


def mount_helper():
    return any(os.path.exists(p) for p in ("/sbin/mount.cifs", "/usr/sbin/mount.cifs")) or shutil.which("mount.cifs")


def smb_mount(c, share, where):
    """One shared folder, opened read-only at where. Older computers get the older ways of talking."""
    if not mount_helper():
        raise Trouble("missing", NEEDS_SETUP)
    unc = f"//{find_host(c['host'])}/{share}"
    opts = ["ro", "noperm", "file_mode=0444", "dir_mode=0555", "iocharset=utf8"]
    if c.get("port"):
        opts.append(f"port={c['port']}")
    with secret_file(smb_login(c)) as login:
        opts.append(f"credentials={login}" if c.get("user") else "guest")
        said = ""
        for vers in ("", "2.0", "1.0"):
            o = opts + ([f"vers={vers}"] if vers else [])
            code, said = run_cmd(["mount", "-t", "cifs", unc, where, "-o", ",".join(o)])
            if code == 0:
                return
            if not re.search(r"error\((95|112|22|121)\)", said):
                break                                  # (only a way of talking it doesn't know is worth another try)
    raise smb_trouble(c, said, bool(c.get("user")))


# ---- SSH (Linux, a Mac) ----------------------------------------------------------------------------
def ssh_target(c):
    check_login("ssh", c["user"])
    host = f"[{c['host']}]" if ":" in c["host"] else c["host"]
    return f"{c['user']}@{host}"


def ssh_options():
    return ["ConnectTimeout=10", "StrictHostKeyChecking=accept-new", f"UserKnownHostsFile={KNOWN_HOSTS}"]


def ssh_cmd(c, *opts):
    cmd = ["ssh", "-T"]
    for o in list(opts) + ssh_options():
        cmd += ["-o", o]
    return cmd + (["-p", str(c["port"])] if c.get("port") else []) + [ssh_target(c)]


ASKPASS = "#!/bin/sh\nprintf '%s\\n' \"$PITATO_SSH_SECRET\"\n"


def password_works(c):
    """True or False: whether SSH takes this password (for the file sharing sshfs uses); None: can't tell."""
    os.makedirs(SECRETS, mode=0o755, exist_ok=True)
    helper = os.path.join(SECRETS, ".askpass")
    try:
        fd = os.open(helper + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o700)
        with os.fdopen(fd, "w") as f:
            f.write(ASKPASS)
        os.replace(helper + ".tmp", helper)
    except OSError:
        return None
    env = dict(os.environ, SSH_ASKPASS=helper, SSH_ASKPASS_REQUIRE="force", DISPLAY=":0",
               PITATO_SSH_SECRET=c.get("password") or "")
    try:
        r = subprocess.run(ssh_cmd(c, "BatchMode=no", "PreferredAuthentications=keyboard-interactive,password",
                                   "NumberOfPasswordPrompts=1") + ["-s", "sftp"],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    said = r.stdout + r.stderr
    if "Permission denied" in said:
        return False
    return True if r.returncode == 0 else None


def ssh_trouble(c, sshfs_said=""):
    """Why SSH didn't let us in: asked again, plainly, to see what it says."""
    addr = c["addr"]
    os.makedirs(os.path.dirname(KNOWN_HOSTS), exist_ok=True)
    code, said = run_cmd(ssh_cmd(c, "BatchMode=yes", "PreferredAuthentications=none") + ["true"], timeout=25)
    if "Could not resolve hostname" in said:
        return Trouble("unknown", f"There's no computer called {c['host']} on this network")
    if "IDENTIFICATION HAS CHANGED" in said or "Host key verification failed" in said:
        return Trouble("hostkey", f"{addr} isn't the computer it was (its SSH key changed). Forget it, then add it again")
    if any(s in said for s in ("Connection refused", "timed out", "No route to host", "Network is unreachable",
                               "Connection closed", "Connection reset")):
        return Trouble("unreachable", f"{addr} isn't answering SSH. Is it on, with SSH turned on?")
    m = re.search(r"Permission denied \(([^)]*)\)", said)
    if m:
        ways = set(m.group(1).split(","))
        if not ways & {"password", "keyboard-interactive"}:
            return Trouble("keys", f"{addr} lets SSH in with keys only, not a password")
        if not c.get("password"):
            return Trouble("login", f"{addr} wants a user name and password")
        works = password_works(c)
        if works is False:
            return Trouble("bad_login", "That user name or password didn't work")
        if works is None and "subsystem request failed" not in said:
            return Trouble("bad_login", "That user name or password didn't work")
    if "subsystem request failed" in said + sshfs_said:
        return Trouble("failed", f"{addr} doesn't share files over SSH (its SFTP is off)")
    last = (sshfs_said or said).strip().splitlines()
    return Trouble("failed", f"Couldn't open {addr}'s files ({last[-1][-60:] if last else 'no answer'})")


def ssh_mount(c, where):
    """The whole computer, as the user signing in sees it, opened read-only at where."""
    if not shutil.which("sshfs"):
        raise Trouble("missing", NEEDS_SETUP)
    if not c.get("user"):
        raise Trouble("login", f"{c['addr']} wants a user name and password")
    opts = ["ro", "allow_other", "reconnect", "follow_symlinks", "ServerAliveInterval=15", "ServerAliveCountMax=3",
            "NumberOfPasswordPrompts=1"] + ssh_options()
    opts.append("password_stdin" if c.get("password") else "BatchMode=yes")
    os.makedirs(os.path.dirname(KNOWN_HOSTS), exist_ok=True)
    cmd = ["sshfs", ssh_target(c) + ":/", where, "-o", ",".join(opts)] + (["-p", str(c["port"])] if c.get("port") else [])
    code, said = run_cmd(cmd, stdin=(c["password"] + "\n") if c.get("password") else "")
    if code != 0 or where not in mounted(os.path.dirname(where)):
        raise ssh_trouble(c, said)


def ssh_home(c, where):
    """Where to start on an SSH computer: the user's own folder (relative to the computer's /)."""
    user = c.get("user") or ""
    if not user or "/" in user or user.startswith("."):
        return ""
    for rel in (["root"] if user == "root" else []) + [f"home/{user}", f"Users/{user}"]:
        if os.path.isdir(os.path.join(where, rel)):
            return rel
    return ""


# ---- the computers added ---------------------------------------------------------------------------
class Computers:
    """The computers added, and their folders opened on this Pi. Used from more than one thread: the screen's and
    the web page's."""

    def __init__(self, path=None, root=None):
        self.path = path or COMPUTERS_FILE
        self.root = root or NET_ROOT
        self.lock = threading.RLock()
        self.opening = {}            # a folder -> its lock: one opening at a time
        self.list = self.load()

    def load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        out = []
        for c in data if isinstance(data, list) else []:
            if isinstance(c, dict) and isinstance(c.get("host"), str) and c.get("how") in ("smb", "ssh"):
                c["port"] = c.get("port") if isinstance(c.get("port"), int) else 0
                c["addr"] = address(c["host"], c["port"])
                out.append(c)
        return out

    def save(self):
        with self.lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + ".tmp"
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(self.list, f, indent=1)
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
            except OSError as ex:
                print(f"couldn't save the computers: {ex}", flush=True)

    def rows(self):
        """The computers, as the screens show them (no passwords)."""
        with self.lock:
            return [{"addr": c["addr"], "key": folder_name(c["addr"]), "how": c["how"], "user": c.get("user", ""),
                     "home": c.get("home", "")} for c in self.list]

    def get(self, addr):
        a = (addr or "").lower()
        with self.lock:
            return next((c for c in self.list if c["addr"].lower() == a or folder_name(c["addr"]).lower() == a), None)

    def folder(self, c, share=""):
        """Where a computer (or one of its shared folders) opens."""
        base = os.path.join(self.root, folder_name(c["addr"]))
        return os.path.join(base, share_dir(share)) if share else base

    def keep(self, c):
        """A computer added, or changed (it keeps its place on the list)."""
        with self.lock:
            at = next((k for k, x in enumerate(self.list) if x["addr"].lower() == c["addr"].lower()), None)
            if at is None:
                self.list = self.list + [c]
            else:
                self.list = self.list[:at] + [c] + self.list[at + 1:]
            self.save()

    def open_lock(self, where):
        with self.lock:
            return self.opening.setdefault(where, threading.Lock())

    # -- adding one ---------------------------------------------------------------------------------
    def add(self, text, user=None, password=None):
        """Looks at the computer typed in (signing in if it asks) and keeps it: (its address, where it starts:
        ("shares", [names]) or ("path", a folder)), or Trouble. Adding one already there signs in again."""
        p = parse(text)
        addr = address(p["host"], p["port"])
        old = self.get(addr) or {}
        user = (user if user is not None else (p["user"] or old.get("user", ""))).strip()
        password = password if password is not None else old.get("password", "")
        host = p["host"]
        if not is_ip(host) and "." not in host and not lookup(host) and lookup(host + ".local"):
            host += ".local"                           # (SSH looks the name up itself: one it can find)
        find_host(host)
        how = p["how"]
        heard = {}
        if not how:
            heard = look(host, [SMB_PORT, SSH_PORT])
            if heard[SMB_PORT] == "open":
                how = "smb"
            elif heard[SSH_PORT] == "open":
                how = "ssh"
            elif "closed" in heard.values():
                raise Trouble("nothing", f"{addr} isn't sharing any files. On Windows, share a folder; "
                                         f"on Linux, turn on SSH")
            else:
                raise Trouble("unreachable", f"{addr} isn't answering. Is it on, and sharing files?")
        check_login(how, user, password)
        c = {"addr": addr, "host": host, "port": p["port"], "how": how, "user": user, "password": password}
        if old and (old["how"], old.get("user"), old.get("password")) != (how, user, password):
            self.close(old)                            # (opened with the old login: open again with this one)
        if how == "smb":
            shares = smb_shares(c)
            if shares:
                self.keep(c)
                if p["share"] and p["share"].lower() in (s.lower() for s in shares):
                    share = next(s for s in shares if s.lower() == p["share"].lower())
                    return addr, ("path", self.open(addr, share))
                return addr, ("shares", shares)
            if heard.get(SSH_PORT) != "open":
                raise Trouble("noshares", f"{addr} isn't sharing any folders yet")
            c["how"] = "ssh"                           # (Samba's there, sharing nothing: SSH, then)
            check_login("ssh", user, password)
        c.pop("home", None)
        where = self.folder(c)
        with self.open_lock(where):
            self.unmount(where)
            os.makedirs(where, exist_ok=True)
            try:
                ssh_mount(c, where)
            except Trouble:
                self.tidy(where)
                raise
            c["home"] = ssh_home(c, where)
        self.keep(c)
        return addr, ("path", os.path.join(where, c["home"]) if c["home"] else where)

    def sign_in(self, addr, user, password):
        """A new user name and password for a computer already added (its folders open again with them)."""
        c = self.get(addr)
        if c is None:
            raise Trouble("gone", "That computer isn't on the list any more")
        trial = dict(c, user=user.strip(), password=password)
        check_login(c["how"], trial["user"], password)
        if c["how"] == "smb":
            smb_shares(trial)                         # (Trouble if they don't work)
            self.close(c)
        else:
            where = self.folder(c)
            with self.open_lock(where):
                self.unmount(where)
                os.makedirs(where, exist_ok=True)
                try:
                    ssh_mount(trial, where)
                except Trouble:
                    self.tidy(where)
                    raise
                trial["home"] = ssh_home(trial, where)
        self.keep(trial)

    # -- opening its folders ----------------------------------------------------------------------
    def shares(self, addr):
        c = self.get(addr)
        if c is None:
            raise Trouble("gone", "That computer isn't on the list any more")
        return smb_shares(c)

    def open(self, addr, share=""):
        """A shared folder (or an SSH computer's /), opened if it isn't yet: where it is on this Pi."""
        c = self.get(addr)
        if c is None:
            raise Trouble("gone", "That computer isn't on the list any more")
        where = self.folder(c, share if c["how"] == "smb" else "")
        if c["how"] == "smb" and not share:
            return self.folder(c)
        with self.open_lock(where):
            if where in mounted(self.root):
                if alive(where):
                    return where
                self.unmount(where)                    # (its connection dropped: opened again)
            os.makedirs(where, exist_ok=True)
            try:
                if c["how"] == "smb":
                    smb_mount(c, share, where)
                else:
                    ssh_mount(c, where)
            except Trouble:
                self.tidy(where)
                raise
            if c["how"] == "ssh":
                home = ssh_home(c, where)
                if home != c.get("home", ""):
                    self.keep(dict(c, home=home))
        return where

    def start(self, addr):
        """Where an SSH computer starts: its user's own folder."""
        c = self.get(addr)
        where = self.open(addr)
        home = (self.get(addr) or c).get("home") or ""
        return os.path.join(where, home) if home else where

    def owner(self, path):
        """Which computer a folder here is on: (its entry, its shared folder or "", where that opens), or None."""
        real = os.path.normpath(path)
        if not real.startswith(self.root + "/"):
            return None
        parts = os.path.relpath(real, self.root).split(os.sep)
        c = self.get(parts[0])
        if c is None:
            return None
        if c["how"] == "smb":
            share = parts[1] if len(parts) > 1 else ""
            return c, share, self.folder(c, share) if share else self.folder(c)
        return c, "", self.folder(c)

    def ensure(self, path):
        """Opens what a folder here is on, if it isn't open (a restart closes them all): or Trouble."""
        found = self.owner(path)
        if found is None:
            raise Trouble("gone", "That computer isn't on the list any more")
        c, share, _ = found
        if c["how"] == "smb" and not share:
            return
        self.open(c["addr"], share)

    def is_top(self, path):
        """A shared folder's own top, or an SSH computer's /: where going up leaves the computer's files."""
        found = self.owner(path)
        return bool(found) and os.path.normpath(path) == found[2]

    # -- closing --------------------------------------------------------------------------------------
    def tidy(self, where):
        """A folder made to open something in, that didn't open: gone again (and its computer's, if empty)."""
        for folder in (where, os.path.dirname(where)):
            if folder != self.root and folder not in mounted(self.root):
                try:
                    os.rmdir(folder)
                except OSError:
                    break

    def unmount(self, where):
        if where in mounted(self.root):
            run_cmd(["umount", "-l", where], timeout=20)
        try:
            os.rmdir(where)
        except OSError:
            pass

    def close(self, c):
        """Every folder of a computer's closed."""
        base = self.folder(c)
        for where in sorted(mounted(self.root), reverse=True):
            if where == base or where.startswith(base + "/"):
                self.unmount(where)

    def forget(self, addr):
        c = self.get(addr)
        if c is None:
            return
        base = self.folder(c)
        self.close(c)
        try:                                           # the empty folders it opened in (never anything inside them)
            for name in os.listdir(base):
                if os.path.join(base, name) not in mounted(self.root):
                    os.rmdir(os.path.join(base, name))
            os.rmdir(base)
        except OSError:
            pass
        if c["how"] == "ssh" and os.path.exists(KNOWN_HOSTS):
            run_cmd(["ssh-keygen", "-R", c["host"] if not c.get("port") else f"[{c['host']}]:{c['port']}",
                 "-f", KNOWN_HOSTS], timeout=10)
        with self.lock:
            self.list = [x for x in self.list if x is not c]
            self.save()

    def close_all(self):
        """Every computer's folders closed (Pitato stopping): quick, and never waits on a computer."""
        for where in sorted(mounted(self.root), reverse=True):
            run_cmd(["umount", "-l", where], timeout=10)
