"""Stands in for logind's hold on a session's console (cage's, there): the console in graphics mode and VT_PROCESS, a
switch away from it or back to it acknowledged as logind does it for a session with a controller; put back (text mode,
VT_AUTO) as logind does when the session's over (SIGTERM, systemctl stop's). argv: the console's number, a log."""
import fcntl
import os
import signal
import struct
import sys

VT_SETMODE, VT_RELDISP, KDSETMODE = 0x5602, 0x5605, 0x4B3A
VT_AUTO, VT_PROCESS, VT_ACKACQ = 0, 1, 2
n, log = int(sys.argv[1]), sys.argv[2]
fd = os.open(f"/dev/tty{n}", os.O_RDWR | os.O_NOCTTY)


def note(s):
    with open(log, "a") as f:
        f.write(s + "\n")


def release(*_):
    fcntl.ioctl(fd, VT_RELDISP, 1)
    note("released")


def acquire(*_):
    fcntl.ioctl(fd, VT_RELDISP, VT_ACKACQ)
    note("acquired")


def bye(*_):
    fcntl.ioctl(fd, VT_SETMODE, struct.pack("bbhhh", VT_AUTO, 0, 0, 0, 0))
    fcntl.ioctl(fd, KDSETMODE, 0)
    note("gone")
    os._exit(0)


signal.signal(signal.SIGUSR1, release)
signal.signal(signal.SIGUSR2, acquire)
signal.signal(signal.SIGTERM, bye)
fcntl.ioctl(fd, KDSETMODE, 1)
fcntl.ioctl(fd, VT_SETMODE, struct.pack("bbhhh", VT_PROCESS, 0, signal.SIGUSR1, signal.SIGUSR2, 0))
note("holding")
while True:
    signal.pause()
