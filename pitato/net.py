"""Other machines on your network (cameras, Ollama, another Pi): their addresses, and requests that
go straight there (never through a proxy) and never back to this Pi by a name that points at it."""
import http.client
import ipaddress
import json
import re
import socket
import time
import urllib.parse
import urllib.request

from .util import UA


CAM_JSON_MAX = 256_000   # bytes: what a camera says is short


def cam_key(addr):
    """One spelling per address, for comparing: no http://, no slash at the end, lower case."""
    a = (addr or "").strip()
    if a.lower().startswith("http://"):
        a = a[7:]
    return a.rstrip("/").lower()


def cam_host(addr):
    """The machine in an address: 192.168.1.50 for 'http://192.168.1.50:5000/stream'."""
    try:
        return (urllib.parse.urlsplit(addr if "://" in addr else "http://" + addr).hostname or "").lower()
    except ValueError:
        return ""


def cam_address(text):
    """A camera address as typed, tidied: an address or a name (a port after it if you like), or
    an http(s) link. None when it isn't one."""
    t = (text or "").strip()
    if not t or len(t) > 200 or any(c.isspace() for c in t):
        return None
    try:
        u = urllib.parse.urlsplit(t if "://" in t else "http://" + t)
        port = u.port
    except ValueError:
        return None
    host = u.hostname or ""
    if u.scheme not in ("http", "https") or not host or not re.fullmatch(r"[a-z0-9.:\-]+", host):
        return None
    if port is not None and not 0 < port < 65536:
        return None
    return t if "://" in t else t.rstrip("/")


def cam_names_pi(host):
    """Does this name or address mean the Pi itself: localhost, 127.0.0.1, ::1, 0.0.0.0, or the
    Pi's own name (which /etc/hosts points at 127.0.1.1)?"""
    h = (host or "").strip("[]").lower().rstrip(".")
    if h in ("localhost", socket.gethostname().lower()) or h.endswith(".localhost"):
        return True
    try:
        a = ipaddress.ip_address(h.split("%")[0])
    except ValueError:
        return False
    a = getattr(a, "ipv4_mapped", None) or a
    return a.is_loopback or a.is_unspecified


def cam_is_local(addr):
    """An address the web page doesn't add: the Pi itself. Anyone on your WiFi can open the
    page, and the Pi's own services are its own."""
    return cam_names_pi(cam_host(addr))


def cam_check_peer(sock, host):
    """A camera reached by a name must not turn out to be the Pi itself (a name can be made to
    point anywhere); one reached by localhost, 127.0.0.1 or the Pi's own name may be."""
    try:
        a = ipaddress.ip_address(sock.getpeername()[0].split("%")[0])
    except (OSError, ValueError, IndexError, TypeError):
        return
    a = getattr(a, "ipv4_mapped", None) or a
    if (a.is_loopback or a.is_unspecified) and not cam_names_pi(host):
        sock.close()
        raise ConnectionRefusedError(f"{host} is this Pi")


def read_capped(r, limit, until, alive=None):
    """An answer read a piece at a time: at most `limit` bytes, all of it by `until` (on
    time.monotonic()), and dropped as soon as alive() says it isn't wanted any more."""
    out, n = [], 0
    read = r.read1 if hasattr(r, "read1") else r.read
    while True:
        if time.monotonic() > until:
            raise TimeoutError("timed out")
        if alive is not None and not alive():
            raise InterruptedError("not wanted any more")
        chunk = read(65536)
        if not chunk:
            return b"".join(out)
        n += len(chunk)
        if n > limit:
            raise ValueError("too big")
        out.append(chunk)


class CamHTTP(http.client.HTTPConnection):
    def connect(self):
        super().connect()
        cam_check_peer(self.sock, self.host)


class CamHTTPS(http.client.HTTPSConnection):
    def connect(self):
        super().connect()
        cam_check_peer(self.sock, self.host)


class CamHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(CamHTTP, req)


class CamHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(CamHTTPS, req, context=self._context)


class CamRedirect(urllib.request.HTTPRedirectHandler):
    """A camera may send us elsewhere, but not on to the Pi itself (unless it's on the Pi)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if cam_names_pi(cam_host(newurl)) and not cam_names_pi(cam_host(req.full_url)):
            return None                               # (the redirect becomes an error)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# cameras and Ollama are on your network: straight there, never through a proxy
CAM_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), CamHTTPHandler, CamHTTPSHandler,
                                         CamRedirect)
OLLAMA_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def cam_open(url, body=None, timeout=3):
    """A request to a camera (JSON when there's a body)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", **UA} if data is not None else dict(UA)
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET", headers=headers)
    return CAM_OPENER.open(req, timeout=timeout)


def cam_json(url, timeout=3):
    with cam_open(url, timeout=timeout) as r:
        out = read_capped(r, CAM_JSON_MAX, time.monotonic() + timeout * 2)
    return json.loads(out) if out.strip() else {}
