"""The Game Boy's link cable between two Pietatos, end to end (screens/together.py's settings for gambatte, its network
link): two real emulators (gambatte, each with a pretend screen of its own) on this machine, as if on two, one the end
the other joins (as the one that asks to link up is), the other joining it at its address. Two tiny test games of our
own, made here: each puts a byte in its link port and sends it (one clocking the cable, the other waiting for it, as
two Game Boys do), its screen white till then; black once the other's byte came (grey: something else came). One
waits for the link's interrupt, the other keeps looking at the port meanwhile (patches/gambatte-link.patch: the byte
comes whole either way). Before the other joins, the one clocking it sees nothing there (as with no cable), and isn't
left waiting; once it does, they link up in a moment (the patch again: not minutes)."""
import os, shutil, sys, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g
import pitato.screens.together as T

S = SP + "/t_link_cable"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Games/gb", "Games/BIOS"):
    os.makedirs(f"{H}/{d}")
os.makedirs(S + "/bin")
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
CORE = SP + "/gambatte/src/gambatte_libretro.so"
g.home_dir = lambda: H
W, HH = 640, 480
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def gb_rom(title, send, expect, clock, look=False):
    """A Game Boy test game: its byte (send) into the link port, then the cable clocked (clock: this one clocks it,
    sending again till the other's byte comes) or waited on; the screen black once the expected byte came, grey if
    something else did. It waits for the link's interrupt (halted), or (look) keeps looking at the port till it's
    done. (Sharp SM83 machine code.)"""
    rom = bytearray(0x8000)
    rom[0x100:0x104] = bytes((0x00, 0xC3, 0x50, 0x01))         # nop; jp $0150
    rom[0x134:0x134 + len(title)] = title.encode()
    code = bytearray((0xF3, 0x31, 0xFE, 0xFF,                    # di; ld sp,$FFFE
                      0x3E, 0x00, 0xE0, 0x47,                    # ld a,0; ldh [BGP],a: white
                      0x3E, 0x08, 0xE0, 0xFF))                   # ld a,8; ldh [IE],a: the link's interrupt only
    again = len(code)
    code += bytes((0xAF, 0xE0, 0x0F,                             # xor a; ldh [IF],a: none waiting
                   0x3E, send, 0xE0, 0x01,                       # ld a,send; ldh [SB],a
                   0x3E, 0x81 if clock else 0x80, 0xE0, 0x02))   # ld a,$81/$80; ldh [SC],a: start
    if look:
        code += bytes((0xF0, 0x02, 0xCB, 0x7F, 0x20, 0xFA))      # ldh a,[SC]; bit 7,a; jr nz,(back): till it's done
    else:
        code += bytes((0x76, 0x00))                              # halt; nop: till it's done
    code += bytes((0xF0, 0x01, 0xFE, expect))                    # ldh a,[SB]; cp expect
    if clock:                                                    # (nobody there yet: 0xFF came, again)
        code += bytes((0x28, 0x02))                              # jr z,got
        code += bytes((0x18, (again - (len(code) + 2)) & 0xFF))  # jr again
    else:
        code += bytes((0x20, 0x06))                              # jr nz,bad
    code += bytes((0x3E, 0xFF, 0xE0, 0x47))                      # got: ld a,$FF; ldh [BGP],a: black
    code += bytes((0x18, 0xFE))                                  # jr $ (done)
    code += bytes((0x3E, 0x55, 0xE0, 0x47, 0x18, 0xFE))          # bad: grey, and done
    rom[0x150:0x150 + len(code)] = code
    rom[0x147], rom[0x148], rom[0x149] = 0x00, 0x00, 0x00        # (a plain cartridge: 32 KB, no save)
    x = 0
    for b in rom[0x134:0x14D]:                                   # (its header's sum)
        x = (x - b - 1) & 0xFF
    rom[0x14D] = x
    return bytes(rom)


A = H + "/Games/gb/Pitato Link A (World).gb"
B = H + "/Games/gb/Pitato Link B (World).gb"
open(A, "wb").write(gb_rom("PITATO LINK A", 0x5A, 0xA5, clock=True))
open(B, "wb").write(gb_rom("PITATO LINK B", 0xA5, 0x5A, clock=False, look=True))


def start(name, rom, options):
    fb = f"{S}/{name}.fb"
    open(fb, "wb").write(bytes(W * HH * 2))
    os.environ["PITATO_FB"] = f"{fb}:{W}x{HH}:16"
    os.makedirs(f"{S}/{name}-saves")
    run = g.GameRun({"path": rom, "title": name, "system": "gb"})
    run.start(CORE, sound="", volume=0, resume=False, cheevos=False, saves=f"{S}/{name}-saves", options=options)
    run.fb = fb
    return run


def shade(run):
    """How light its screen is, in the middle (the whole of the Game Boy's screen is one shade: its palette's)."""
    px = int(np.fromfile(run.fb, dtype="<u2").reshape(HH, W)[HH // 2, W // 2])
    v = (((px >> 11) & 31) * 8 + ((px >> 5) & 63) * 4 + (px & 31) * 8) / 3
    return "white" if v > 170 else "black" if v < 60 else "grey"


def listening(port):
    """Something on this machine listens on that port (from the kernel's own list: not a connection to it, which
    the game would take for the other)."""
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            rows = open(f).read().splitlines()[1:]
        except OSError:
            continue
        if any(r.split()[1].endswith(f":{port:04X}") and r.split()[3] == "0A" for r in rows):
            return True
    return False


def until(cond, secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.1)
    return cond()


check("the settings: the one asking is the end the other joins; the other joins it at its address",
      T.link_options(True) == ["gambatte_gb_link_mode=Network Server", "gambatte_gb_link_network_port=56400"]
      and T.link_options(False, "127.0.0.1")[0] == "gambatte_gb_link_mode=Network Client")
one = start("one", A, T.link_options(True))
started = one.wait_started(20) and until(lambda: shade(one) == "white", 10)
check(f"the one that asked: its game starts (white: nothing came yet) ({shade(one)})", started)
time.sleep(1.0)
check(f"...nobody linked yet: it clocks the cable and nothing's there (as with no cable), not left waiting "
      f"({shade(one)}, {one.alive()})", shade(one) == "white" and one.alive())
check("...the end the other joins, open (listening on its port)", listening(T.LINK_PORT))
two = start("two", B, T.link_options(False, "127.0.0.1"))
check("the other joins it", two.wait_started(20))
came = until(lambda: shade(one) == "black" and shade(two) == "black", 30)
check(f"the cable clocked: each one's byte came across, both black ({shade(one)}, {shade(two)})", came)
for run in (one, two):
    run.quit(5)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
