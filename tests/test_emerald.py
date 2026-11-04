"""The Emerald AI player (pitato/emerald.py), on a pretend Pokémon Emerald: a cartridge and working memory made
here at the addresses the real game uses (its map headers, tiles, people, your Pokémon encrypted as the game keeps
them, a battle, its menus), and a pretend game that answers the buttons (walking a tile per step, a door, a road
onto the next map, the battle's menus, a yes or no, a script's menu, the summary screen's move cursor). Checked: what
it reads (where you are, the doors and roads and people, your team, a battle), the choices the model gets (and the
goal), and that what's picked gets done: walking a path, through a door, along a road, a battle's move picked in its
menus, a yes or no, a choice, text read on, a move forgotten for a new one."""
import os, struct, sys, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, ROOT)
from pitato import emerald as E

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- the game's letters, and a cartridge and memory to put things in ---------------------------------------------
ENC = {v: k for k, v in E.CHARS.items() if len(v) == 1}


def enc(s, n=None):
    b = bytes(ENC[c] for c in s) + b"\xff"
    if n:
        b = (b + b"\xff" * n)[:n]
    return b


ROM = bytearray(0x600000)
EW, IW = bytearray(E.EWRAM_SIZE), bytearray(E.IWRAM_SIZE)


def put(addr, data):
    if addr >= E.ROM_BASE:
        ROM[addr - E.ROM_BASE:addr - E.ROM_BASE + len(data)] = data
    elif addr >= E.IWRAM:
        IW[addr - E.IWRAM:addr - E.IWRAM + len(data)] = data
    else:
        EW[addr - E.EWRAM:addr - E.EWRAM + len(data)] = data


def p8(a, v): put(a, struct.pack("<B", v))
def p16(a, v): put(a, struct.pack("<H", v))
def p32(a, v): put(a, struct.pack("<I", v))
def g8(a): return E.Mem(bytes(IW), bytes(EW), bytes(ROM)).u8(a)


ROM[0xA0:0xAC] = b"POKEMON EMER"
ROM[0xAC:0xB0] = b"BPEE"
ROM[0xBC] = 0
check(f"the cartridge's Emerald, English: played ({E.supported(bytes(ROM))}); another game isn't",
      E.supported(bytes(ROM)) and not E.supported(b"\0" * 0x200))

# names, moves, types
TORCHIC, TREECKO, MUDKIP = 280, 277, 283
for s, name, t in ((TORCHIC, "TORCHIC", 10), (TREECKO, "TREECKO", 12), (MUDKIP, "MUDKIP", 11)):
    put(E.SPECIES_NAMES + 11 * s, enc(name, 11))
    put(E.SPECIES_INFO + 28 * s + 6, bytes((t, t)))
SCRATCH, GROWL, EMBER, TACKLE, WATER_GUN, CUT = 10, 45, 52, 33, 55, 15
for mv, name, power, t, acc, pp in ((SCRATCH, "SCRATCH", 40, 0, 100, 35), (GROWL, "GROWL", 0, 0, 100, 40),
                                    (EMBER, "EMBER", 40, 10, 100, 25), (TACKLE, "TACKLE", 35, 0, 95, 35),
                                    (WATER_GUN, "WATER GUN", 40, 11, 100, 25), (CUT, "CUT", 50, 0, 95, 30)):
    put(E.MOVE_NAMES + 13 * mv, enc(name, 13))
    put(E.BATTLE_MOVES + 12 * mv, bytes((0, power, t, acc, pp)))
put(E.TYPE_EFFECTIVENESS, bytes((10, 12, 20, 12, 10, 5, 11, 10, 20, 0xFF)))

# maps: Route 101 (with a door to Professor Birch's Lab, a road north to Oldale Town), Oldale Town, the Lab, and your
# room upstairs at home (a boy's: Brendan's house), with the clock on its wall
ROUTE101, OLDALE, LAB, BEDROOM = (0, 16), (0, 10), (1, 4), (1, 1)
GROUP_TABLES = {0: 0x08101000, 1: 0x08101200, 11: 0x08101400, 24: 0x08101600}
for g, table in GROUP_TABLES.items():
    p32(E.MAP_GROUPS + 4 * g, table)
# ...and further on: Route 104, in two parts a wall apart (the south part's door into Petalburg Woods, the north
# part's out of them, and the road north to Rustboro City), the woods, Rustboro City and its Gym
R104, WOODS, RUSTBORO, RGYM = (0, 19), (24, 11), (0, 3), (11, 3)
HEADERS = {ROUTE101: 0x08100000, OLDALE: 0x08100040, LAB: 0x08100080, BEDROOM: 0x081000C0, R104: 0x08100100,
           WOODS: 0x08100140, RUSTBORO: 0x08100180, RGYM: 0x081001C0}
for (g, n), h in HEADERS.items():
    p32(GROUP_TABLES[g] + 4 * n, h)
TILESETS = (0x08103000, 0x08103100)
ATTRS = 0x08104000
for k, mb in {1: 0, 2: E.MB_TALL_GRASS, 3: E.MB_ANIMATED_DOOR, 4: 0, 5: 101, 6: E.MB_COUNTER, 7: 59, 8: 18}.items():
    p16(ATTRS + 2 * k, mb)
p32(TILESETS[0] + 0x10, ATTRS)
p32(TILESETS[1] + 0x10, ATTRS + 0x400)
LAYOUTS = {ROUTE101: 0x08102000, OLDALE: 0x08102020, LAB: 0x08102040, BEDROOM: 0x08102060, R104: 0x08102080,
           WOODS: 0x081020A0, RUSTBORO: 0x081020C0, RGYM: 0x081020E0}
for key, lay in LAYOUTS.items():
    put(lay, struct.pack("<ii", 10, 10))
    p32(lay + 0x10, TILESETS[0])
    p32(lay + 0x14, TILESETS[1])
# Route 101's people and door, and its road
EVENTS = 0x08106000
put(EVENTS, bytes((4, 1, 0, 0)))
p32(EVENTS + 4, 0x08106100)
p32(EVENTS + 8, 0x08106200)            # (MapEvents: warps at +8)
TRAINER_SCRIPT, ITEM_SCRIPT, TALK_SCRIPT = 0x08107000, 0x08107100, 0x08107200
put(TRAINER_SCRIPT, bytes((E.SCR_OP_TRAINERBATTLE, 0)) + struct.pack("<H", 5))
put(ITEM_SCRIPT, bytes((0x02,)))
put(TALK_SCRIPT, bytes((0x02,)))
for k, (lid, gfx, script) in enumerate(((1, 5, TRAINER_SCRIPT), (2, E.GFX_ITEM_BALL, ITEM_SCRIPT), (3, 10, TALK_SCRIPT),
                                        (5, 97, E.SCR_BIRCHS_BAG))):   # (5: Professor Birch's bag, out of sight)
    a = 0x08106100 + 0x18 * k
    put(a, bytes((lid, gfx)))
    p32(a + 0x10, script)
put(0x08106200, struct.pack("<hhBBBB", 5, 2, 0, 0, LAB[1], LAB[0]))   # the door at (5, 2): to the Lab
CONNS = 0x08106300
put(CONNS, struct.pack("<iI", 1, CONNS + 8))
put(CONNS + 8, struct.pack("<BxxxiBB", 2, 0, OLDALE[0], OLDALE[1]))   # north: Oldale Town
OLDALE_CONNS = 0x08106340
put(OLDALE_CONNS, struct.pack("<iI", 1, OLDALE_CONNS + 8))
put(OLDALE_CONNS + 8, struct.pack("<BxxxiBB", 1, 0, ROUTE101[0], ROUTE101[1]))
LAB_EVENTS = 0x08106400
put(LAB_EVENTS, bytes((0, 1, 0, 0)))
p32(LAB_EVENTS + 8, 0x08106480)
put(0x08106480, struct.pack("<hhBBBB", 5, 9, 0, 0, 127, 127))
for key, h in HEADERS.items():
    p32(h, LAYOUTS[key])
p32(HEADERS[ROUTE101] + 4, EVENTS)
p32(HEADERS[ROUTE101] + 0xC, CONNS)
p32(HEADERS[OLDALE] + 0xC, OLDALE_CONNS)
p32(HEADERS[LAB] + 4, LAB_EVENTS)
BED_EVENTS = 0x08106500                 # your room: no people or doors, one thing to look at (the clock, at 5, 1)
put(BED_EVENTS, bytes((0, 0, 0, 1)))
p32(BED_EVENTS + 0x10, 0x08106580)
put(0x08106580, struct.pack("<HHBBxxI", 5, 1, 0, 0, E.SCR_WALL_CLOCK[0]))
p32(HEADERS[BEDROOM] + 4, BED_EVENTS)
RT101_BLOCKS = 0x08105000               # Route 101's own tiles, in the cartridge: tall grass among them
p32(LAYOUTS[ROUTE101] + 0xC, RT101_BLOCKS)
put(RT101_BLOCKS, struct.pack("<100H", *([1 | 3 << 12] * 95 + [2 | 3 << 12] * 5)))
FAR_EVENTS = {R104: 0x08106600, WOODS: 0x08106700, RUSTBORO: 0x08106800, RGYM: 0x08106900}
FAR_WARPS = {R104: [(2, 6, WOODS, 0), (2, 2, WOODS, 1)], WOODS: [(1, 8, R104, 0), (8, 1, R104, 1)],
             RUSTBORO: [(5, 2, RGYM, 0)], RGYM: [(5, 9, RUSTBORO, 0)]}
for key, ev in FAR_EVENTS.items():
    put(ev, bytes((0, len(FAR_WARPS[key]), 0, 0)))
    p32(ev + 8, ev + 0x40)
    for k, (x, y, to, w) in enumerate(FAR_WARPS[key]):
        put(ev + 0x40 + 8 * k, struct.pack("<hhBBBB", x, y, 0, w, to[1], to[0]))
    p32(HEADERS[key] + 4, ev)
FAR_CONNS = {R104: (0x08106A00, 2, RUSTBORO), RUSTBORO: (0x08106A40, 1, R104)}
for key, (c, d, to) in FAR_CONNS.items():
    put(c, struct.pack("<iI", 1, c + 8))
    put(c + 8, struct.pack("<BxxxiBB", d, 0, to[0], to[1]))
    p32(HEADERS[key] + 0xC, c)
for key in (R104, WOODS, RUSTBORO, RGYM):
    p32(HEADERS[key], LAYOUTS[key])
LAYOUT_IDS = {ROUTE101: 17, OLDALE: 18, LAB: 19, BEDROOM: 20, R104: 21, WOODS: 22, RUSTBORO: 23, RGYM: 24}
# a script's menu (multichoice 3): HEAL, SHOP, LEAVE
MC = 0x08108000
for k, word in enumerate(("HEAL", "SHOP", "LEAVE")):
    put(MC + 0x40 + 16 * k, enc(word))
    p32(MC + 8 * k, MC + 0x40 + 16 * k)
put(E.MULTICHOICE_LISTS + 8 * 3, struct.pack("<IB", MC, 3))

# ---- working memory: the save blocks, your team, where you are -----------------------------------------------------
SB1, SB2 = 0x02031000, 0x02030000
p32(E.G_SAVEBLOCK1_PTR, SB1)
p32(E.G_SAVEBLOCK2_PTR, SB2)
p32(SB2 + E.SB2_ENCRYPTION_KEY, 0x1234)
p32(SB1 + E.SB1_MONEY, 3000 ^ 0x1234)


def set_flag(flag, on=True):
    a = SB1 + E.SB1_FLAGS + flag // 8
    v = g8(a)
    p8(a, (v | (1 << flag % 8)) if on else (v & ~(1 << flag % 8)))


set_flag(E.FLAG_SYS_POKEMON_GET)
set_flag(E.FLAG_DEFEATED_RIVAL_ROUTE103)      # the goal now: Professor Birch's Lab, for the Pokédex


def pokemon(slot, personality, otid, species, nick, level, hp, max_hp, moves, pps):
    key = personality ^ otid
    gpos, apos = E.SUBSTRUCT_POS[personality % 24]
    subs = [bytes(12)] * 4
    subs[gpos] = struct.pack("<HHIBBH", species, 0, 1000, 0, 70, 0)
    subs[apos] = struct.pack("<4H4B", *moves, *pps)
    others = [i for i in range(4) if i not in (gpos, apos)]
    for i in others:
        subs[i] = bytes(12)
    plain = b"".join(subs)
    secure = struct.pack("<12I", *(v ^ key for v in struct.unpack("<12I", plain)))
    box = struct.pack("<II", personality, otid) + enc(nick, 10) + bytes((2, 2)) + bytes(7) + bytes(1) + bytes(4) + secure
    full = box + struct.pack("<IBBHHHHHHH", 0, level, 0, hp, max_hp, 20, 20, 20, 20, 20)
    assert len(full) == 100, len(full)
    put(E.G_PLAYER_PARTY + 100 * slot, full)


pokemon(0, 0x1A2B3C4D, 0x55667788, TORCHIC, "BLAZE", 12, 30, 34, (SCRATCH, GROWL, EMBER, CUT), (30, 40, 20, 30))
pokemon(1, 0x0BADF00D, 0x55667788, MUDKIP, "MUDDY", 9, 0, 28, (TACKLE, WATER_GUN, 0, 0), (35, 25, 0, 0))
p8(E.G_PLAYER_PARTY_COUNT, 2)
rom_tables = E.Rom(bytes(ROM))
team = E.party(E.Mem(bytes(IW), bytes(EW), bytes(ROM)), rom_tables)
check(f"your team, from its encrypted data: {[(p['name'], p['species'], p['level'], p['hp']) for p in team]}, "
      f"{[[rom_tables.move(m)['name'] for m, _ in p['moves']] for p in team]}",
      [(p["name"], p["species"], p["level"], p["hp"], p["max_hp"]) for p in team]
      == [("BLAZE", TORCHIC, 12, 30, 34), ("MUDDY", MUDKIP, 9, 0, 28)]
      and [m for m, _ in team[0]["moves"]] == [SCRATCH, GROWL, EMBER, CUT] and team[0]["moves"][2] == (EMBER, 20)
      and [m for m, _ in team[1]["moves"]] == [TACKLE, WATER_GUN])

# the map: Route 101, 10 x 10, with 7 tiles of what's around on each side
W, H = 10 + 15, 10 + 14
VMAP = 0x0201C000


def block(metatile, collision=0, elev=3):
    return metatile | (collision << 10) | (elev << 12)


def load_map(key):
    p32(E.G_MAP_HEADER, LAYOUTS[key])
    p32(E.G_MAP_HEADER + 4, {ROUTE101: EVENTS, LAB: LAB_EVENTS, BEDROOM: BED_EVENTS}.get(key, FAR_EVENTS.get(key, 0)))
    p32(E.G_MAP_HEADER + 0xC, {ROUTE101: CONNS, OLDALE: OLDALE_CONNS}.get(key, FAR_CONNS.get(key, (0,))[0]))
    p16(E.G_MAP_HEADER + 0x12, LAYOUT_IDS[key])
    p8(SB1 + E.SB1_LOCATION, key[0])
    p8(SB1 + E.SB1_LOCATION + 1, key[1])
    put(E.G_BACKUP_MAP_LAYOUT, struct.pack("<iiI", W, H, VMAP))
    tiles = [E.BLOCK_UNDEFINED] * (W * H)
    for y in range(7, 17):
        for x in range(7, 17):
            tiles[x + W * y] = block(1)
    if key == ROUTE101:
        for x in range(7, 17):                      # a fence along the top, a gap at x 10 (the road north)
            if x != 10:
                tiles[x + W * 7] = block(4, 1)
        for y in range(0, 7):                       # Oldale Town's edge, up the road
            for x in range(7, 17):
                tiles[x + W * y] = block(1)
        tiles[12 + W * 9] = block(3, 1)             # the Lab's door (map 5, 2)
        for x in (8, 9):
            for y in (13, 14):
                tiles[x + W * y] = block(2)          # tall grass
        tiles[13 + W * 15] = block(7, 1)             # a ledge, jumped going south (can't be walked onto)
    if key == R104:                                  # a wall across, between its two parts; Rustboro up the road
        for x in range(7, 17):
            tiles[x + W * 11] = block(4, 1)
        for y in range(0, 7):
            for x in range(7, 17):
                tiles[x + W * y] = block(1)
    if key == BEDROOM:                               # the wall along the top (the clock's on it)
        for x in range(7, 17):
            tiles[x + W * 7] = tiles[x + W * 8] = block(4, 1)
    if key == LAB:
        tiles[12 + W * 16] = block(5)                # the way out: a mat, walked off going south
        for x in range(7, 17):
            tiles[x + W * 7] = block(4, 1)
    put(VMAP, struct.pack(f"<{W * H}H", *tiles))
    return tiles


def put_object(i, local_id, gfx, x, y, trainer=0, player=False, active=True, invisible=False, elev=3):
    a = E.G_OBJECT_EVENTS + E.OBJECT_EVENT_SIZE * i
    bits = (1 if active else 0) | ((1 << 16) if player else 0) | ((1 << 13) if invisible else 0)
    p32(a, bits)
    put(a + 5, bytes((gfx, 0, trainer, local_id, 16, 0, elev)))
    put(a + 0x10, struct.pack("<hhhh", x, y, x, y))
    p16(a + 0x18, E.SOUTH)


TILES = load_map(ROUTE101)
put_object(0, 0xFF, 0, 10, 12, player=True)
put_object(1, 1, 5, 14, 12, trainer=1)
put_object(2, 2, E.GFX_ITEM_BALL, 8, 10)
put_object(3, 3, 10, 15, 15)
p8(E.G_PLAYER_AVATAR, 1)
p8(E.G_PLAYER_AVATAR + 5, 0)
p32(E.G_MAIN + 4, E.CB2_OVERWORLD | 1)


# ---- the pretend game: it answers the buttons ----------------------------------------------------------------------
class Clock:
    t = 1000.0

    @classmethod
    def monotonic(cls):
        return cls.t


E.time = types.SimpleNamespace(monotonic=Clock.monotonic)
DIRS = {"up": E.NORTH, "down": E.SOUTH, "left": E.WEST, "right": E.EAST}


class Game:
    STEP = 0.25                                  # seconds a step takes (you're on the next tile as it starts)

    def __init__(self):
        self.held, self.map = set(), ROUTE101
        self.step_end = None                     # a step under way: when it's over
        self.steps = 0
        self.taps, self.picks, self.decisions, self.done = [], [], [], []
        self.statuses = []
        self.talks = []                          # A out walking, standing: the tile you faced
        self.on_tap = None                       # (a screen's own buttons: a battle's menus...)
        self.logs = []

    # the player and the map
    def me(self):
        a = E.G_OBJECT_EVENTS
        m = E.Mem(bytes(IW), bytes(EW), bytes(ROM))
        return m.s16(a + 0x10), m.s16(a + 0x12)

    def facing(self):
        return E.Mem(bytes(IW), bytes(EW), bytes(ROM)).u16(E.G_OBJECT_EVENTS + 0x18) & 0xF

    def move_me(self, x, y, facing):
        a = E.G_OBJECT_EVENTS
        put(a + 0x10, struct.pack("<hhhh", x, y, x, y))
        p16(a + 0x18, facing)

    def walking(self):
        return g32(E.G_MAIN + 4) & ~1 == E.CB2_OVERWORLD

    def walk_tap(self, b):
        """A button tapped out walking, as the game takes it: only while you're standing (mid-step it's lost). A
        direction turns you that way (or steps, if you're facing it already); A talks to whoever you face."""
        if not self.walking() or self.step_end is not None:
            return
        if b in DIRS:
            if self.facing() != DIRS[b]:
                p16(E.G_OBJECT_EVENTS + 0x18, DIRS[b])
            else:
                self.try_step(DIRS[b])
        elif b == "a":
            x, y = self.me()
            dx, dy = E.STEP[self.facing()]
            self.talks.append((x + dx, y + dy))

    def blocked(self, x, y):
        t = TILES[x + W * y] if 0 <= x < W and 0 <= y < H else E.BLOCK_UNDEFINED
        if t == E.BLOCK_UNDEFINED or (t >> 10) & 3:
            return True
        m = E.Mem(bytes(IW), bytes(EW), bytes(ROM))
        for i in range(1, 16):
            a = E.G_OBJECT_EVENTS + E.OBJECT_EVENT_SIZE * i
            if m.u32(a) & 1 and (m.s16(a + 0x10), m.s16(a + 0x12)) == (x, y):
                return True
        return False

    def tick(self, dt):
        Clock.t += dt
        if not self.walking():
            return
        if self.step_end is not None:            # a step under way: over yet?
            if Clock.t < self.step_end:
                return
            self.step_end = None
            p8(E.G_PLAYER_AVATAR + 3, 0)
        dirs = [DIRS[b] for b in self.held if b in DIRS]
        if dirs:                                 # (held: the next step, straight on)
            self.try_step(dirs[0])

    def try_step(self, d):
        x, y = self.me()
        dx, dy = E.STEP[d]
        if self.map == ROUTE101 and d == E.NORTH and (x, y - 1) == (12, 9):     # the door: into the Lab
            self.warp(LAB, 12, 15)
            return
        if self.map == LAB and d == E.SOUTH and (x, y) == (12, 16):              # the mat, walked off south: out
            self.warp(ROUTE101, 12, 10)
            return
        nx, ny = x + dx, y + dy
        jump = self.map == ROUTE101 and TILES[nx + W * ny] & 0x3FF == 7 and d == E.SOUTH
        if jump:                                 # a ledge: over it
            nx, ny = nx + dx, ny + dy
        if self.blocked(nx, ny):
            p16(E.G_OBJECT_EVENTS + 0x18, d)     # (a bump: facing that way)
            return
        self.move_me(nx, ny, d)
        self.steps += 1
        p8(E.G_PLAYER_AVATAR + 3, 1)
        self.step_end = Clock.t + self.STEP * (2 if jump else 1)
        if self.map == ROUTE101 and ny < 7:      # up the road: Oldale Town
            self.warp(OLDALE, nx, ny + 10)

    def warp(self, key, x, y):
        global TILES
        self.map = key
        TILES = load_map(key)
        for i in range(1, 4):
            p32(E.G_OBJECT_EVENTS + E.OBJECT_EVENT_SIZE * i, 0)
        self.move_me(x, y, E.NORTH)
        self.step_end = None
        p8(E.G_PLAYER_AVATAR + 3, 0)
        self.done.append(("arrived", E.MAP_NAMES[key[0]][key[1]]))


def g32(a):
    return E.Mem(bytes(IW), bytes(EW), bytes(ROM)).u32(a)


def walked():
    """The last walk it picked by itself (the model not asked): its log entry."""
    return next((e for e in reversed(game.logs) if e.get("kind") == "walk"), {})


class FakeIO:
    def __init__(self, game):
        self.g = game

    def snapshot(self):
        self.g.tick(0.01)
        return E.Mem(bytes(IW), bytes(EW), bytes(ROM))

    def peek(self, *ranges):
        m = E.Mem(bytes(IW), bytes(EW), bytes(ROM))
        return [m.bytes(a, n) for a, n in ranges]

    def peek_u8(self, a):
        return self.peek((a, 1))[0][0]

    def peek_s8(self, a):
        v = self.peek_u8(a)
        return v - 256 if v > 127 else v

    def peek_u32(self, a, code=False):
        v = struct.unpack("<I", self.peek((a, 4))[0])[0]
        return v & ~1 if code else v

    def tap(self, b):
        self.g.taps.append(b)
        (self.g.on_tap or self.g.walk_tap)(b)
        self.g.tick(0.05)

    def hold(self, b):
        self.g.held.add(b)

    def release(self, b):
        self.g.held.discard(b)

    def wait(self, secs):
        steps = max(1, int(secs / 0.03))
        for _ in range(steps):
            self.g.tick(secs / steps)

    def decide(self, kind, says, state, choices, fallback):
        self.g.decisions.append((kind, state, dict(choices), fallback))
        if self.g.picks:
            want = self.g.picks.pop(0)
            pick = next((k for k in choices if want in k or want in choices[k]), fallback)
        else:
            pick = fallback
        return pick

    def status(self, words):
        self.g.statuses.append(words)

    def log(self, **kw):
        self.g.logs.append(kw)


game = Game()
io = FakeIO(game)
player = E.Emerald(bytes(ROM), io)

# ---- reading the map --------------------------------------------------------------------------------------------
m = io.snapshot()
f = E.Field(m, player.rom)
check(f"where you are: {f.name}, at map ({f.x - 7}, {f.y - 7}), {len(f.people)} people, doors {f.warps}, "
      f"roads {f.roads}", f.name == "Route 101" and (f.x, f.y) == (10, 12) and len(f.people) == 3
      and f.warps == [(12, 9, LAB)] and f.roads == [(E.NORTH, 0, OLDALE)])
check(f"...free to walk: {player.mode(m)}", player.mode(m) == ("walk",))
opts = player.options(m, f)
words = {k: o["words"] for k, o in opts.items()}
for k, v in sorted(words.items()):
    print("       ", k, ":", v)
check("...the choices: the Lab's door (toward the goal: the Pokédex), the road north, the trainer, the item, the person, "
      "the grass, places not seen",
      "toward your goal" in words.get("door0", "") and "Professor Birch's Lab" in words["door0"]
      and words.get("road2", "").startswith("Go north to Oldale Town") and "Battle the trainer" in words.get("talk1", "")
      and "Pick up the item" in words.get("talk2", "") and "Talk to the person" in words.get("talk3", "")
      and "grass" in opts and "explore" in opts)
st = player.state(m)
check(f"...the model's told the goal, where, the team, the money: {st['goal'][:50]}..., {st['where']}, "
      f"{st['team']}, ${st['money']}", "Pokédex" in st["goal"] and st["where"] == "Route 101"
      and st["team"][0] == {"name": "BLAZE", "level": 12, "hp": "30/34"} and st["money"] == 3000 and st["badges"] == 0)
check(f"...and it'd go for the goal if the model can't say ({player.fallback(m, f, opts)})",
      player.fallback(m, f, opts) == "door0")
set_flag(E.TRAINER_FLAGS_START + 5)
opts2 = player.options(io.snapshot(), E.Field(io.snapshot(), player.rom))
check(f"...a trainer beaten is just someone to talk to ({opts2['talk1']['words']})",
      opts2["talk1"]["words"].startswith("Talk to the person"))
set_flag(E.TRAINER_FLAGS_START + 5, False)
seen, tiles = f.reach()
check(f"...a ledge jumped going south (to {(13, 16) in tiles}), never climbed back up",
      (13, 16) in tiles and f.step(13, 16, 3, E.NORTH, {}, set(), False) is None)
put_object(4, 4, 10, 11, 12, invisible=True)     # someone unseen (a script's) next to you: in the way, not talked to
f4 = E.Field(io.snapshot(), player.rom)
_, t4 = f4.reach()
put_object(4, 4, 10, 11, 12, elev=4)             # someone at another height (on a bridge over you): not in the way
f5 = E.Field(io.snapshot(), player.rom)
_, t5 = f5.reach()
check(f"someone unseen is in the way ({(11, 12) not in t4}) but not someone to talk to "
      f"({[p['local_id'] for p in f4.people]}); someone at another height isn't in the way ({(11, 12) in t5})",
      (11, 12) not in t4 and 4 not in [p["local_id"] for p in f4.people] and (11, 12) in t5)
p32(E.G_OBJECT_EVENTS + E.OBJECT_EVENT_SIZE * 4, 0)

# ---- doing it: through the door ---------------------------------------------------------------------------------
asked = len(game.decisions)
player.on_walk(io.snapshot())
check(f"the way toward the goal: the Lab's door, walked to, up through it, into the Lab ({game.done}, "
      f"{game.statuses[-1:]})", ("arrived", "Littleroot Town, Professor Birch's Lab") in game.done and game.map == LAB)
check(f"...without asking the model: the way's known ({walked()})", len(game.decisions) == asked
      and walked().get("by") == "story" and walked().get("pick") == "door0")
# out of the Lab: its mat (a way back where you came from)
put(SB1 + E.SB1_DYNAMIC_WARP, bytes(ROUTE101))
game.move_me(12, 13, E.NORTH)
m = io.snapshot()
lab_opts = player.options(m, E.Field(m, player.rom))
check(f"in the Lab: the way out, back to where you came in ({lab_opts.get('door0', {}).get('words')})",
      lab_opts.get("door0", {}).get("words", "").startswith("Go to Route 101"))
game.done.clear()
game.picks = ["door0"]
player.on_walk(io.snapshot())
check(f"...there, with no way on known (no one to see), the model's asked ({game.decisions[-1][0]}, "
      f"{sorted(game.decisions[-1][2])}): its pick, onto the mat, off it going south, out ({game.done})",
      game.decisions[-1][0] == "walk" and "goal" in game.decisions[-1][1] and ("arrived", "Route 101") in game.done
      and game.map == ROUTE101)
set_flag(E.FLAG_SYS_POKEDEX_GET)               # (on in the story: to your dad at the Petalburg City Gym, a way this
                                               # pretend world doesn't have: the model picks where to go)

# back on Route 101, then up the road north
game.warp(ROUTE101, 10, 12)
for i, (lid, gfx, x, y, tr) in enumerate(((1, 5, 14, 12, 1), (2, E.GFX_ITEM_BALL, 8, 10, 0), (3, 10, 15, 15, 0)), 1):
    put_object(i, lid, gfx, x, y, trainer=tr)
game.done.clear()
game.picks = ["road2"]
player.on_walk(io.snapshot())
check(f"the road north: walked up it onto Oldale Town ({game.done})", ("arrived", "Oldale Town") in game.done)
game.warp(ROUTE101, 10, 12)
for i, (lid, gfx, x, y, tr) in enumerate(((1, 5, 14, 12, 1), (2, E.GFX_ITEM_BALL, 8, 10, 0), (3, 10, 15, 15, 0)), 1):
    put_object(i, lid, gfx, x, y, trainer=tr)

# talking to the person: next to them, facing them, A
game.taps.clear()
game.picks = ["talk3"]
player.on_walk(io.snapshot())
x, y = game.me()
check(f"talking to someone: next to them ({x}, {y}, they're at 15, 15), facing them, A once the last step's over "
      f"(the game takes it only standing: talked to {game.talks[-1:]}, {game.taps[-2:]})",
      abs(x - 15) + abs(y - 15) == 1 and game.taps[-1] == "a" and game.talks[-1:] == [(15, 15)]
      and g8(E.G_PLAYER_AVATAR + 3) == 0)
for _ in range(2):
    game.picks = ["talk3"]
    player.on_walk(io.snapshot())
game.picks = ["talk3"]
player.on_walk(io.snapshot())
check(f"talking to the same person three times: not offered a fourth ({sorted(game.decisions[-1][2])})",
      "talk3" not in game.decisions[-1][2] and "talk1" in game.decisions[-1][2])

# (the fourth time, the model's pick wasn't offered: it did what it'd do if the model couldn't say. Back to Route 101)
check(f"...and with the model's pick not offered, it did something that was ({game.decisions[-1][3]})",
      game.decisions[-1][3] in game.decisions[-1][2])
game.warp(ROUTE101, 10, 12)
for i, (lid, gfx, x, y, tr) in enumerate(((1, 5, 14, 12, 1), (2, E.GFX_ITEM_BALL, 8, 10, 0), (3, 10, 15, 15, 0)), 1):
    put_object(i, lid, gfx, x, y, trainer=tr)

# water: not without Surf; surfing, across it, and off onto land
lake = [(x, y) for x in range(11, 14) for y in range(14, 17)]
saved = list(TILES)
for x, y in lake:
    TILES[x + W * y] = block(8, 0, 1)              # (metatile 8: deep water)
put(VMAP, struct.pack(f"<{W * H}H", *TILES))
game.move_me(10, 15, E.EAST)
f = E.Field(io.snapshot(), player.rom)
_, t1 = f.reach()
check(f"surfing starts from the shore: facing the water from the land ({player.shore(f, t1)})",
      player.shore(f, t1) == (10, 15, E.EAST))
f.surfing, f.elev = True, 1
f.x, f.y = 11, 15
_, t2 = f.reach()
check(f"water: not walked into ({(12, 15) in t1}); surfing, across it ({(13, 15) in t2}) and off onto the far side "
      f"({(14, 15) in t2})", (12, 15) not in t1 and (13, 15) in t2 and (14, 15) in t2)
TILES[:] = saved
put(VMAP, struct.pack(f"<{W * H}H", *TILES))

# tall grass: back and forth in it, each step over before the next (the way turns each time)
E.GRASS_STEPS = 6
game.move_me(8, 13, E.SOUTH)
game.steps = 0
player.pace()
check(f"walking in the grass for a wild Pokémon: back and forth ({game.steps} steps, at {game.me()})",
      game.steps == 6 and game.me() == (8, 13))
E.GRASS_STEPS = 40
game.move_me(10, 12, E.SOUTH)

# ---- a battle ----------------------------------------------------------------------------------------------------------
def battle_mon(b, species, nick, level, hp, max_hp, types, moves, pps, stats=(30, 30, 30, 30, 30)):
    a = E.G_BATTLE_MONS + E.BATTLE_MON_SIZE * b
    put(a, struct.pack("<6H", species, *stats))
    put(a + 0xC, struct.pack("<4H", *moves))
    put(a + 0x21, bytes(types))
    put(a + 0x24, bytes(pps))
    put(a + 0x28, struct.pack("<HBBH", hp, level, 0, max_hp))
    put(a + 0x30, enc(nick, 11))


p32(E.G_MAIN + 4, E.CB2_BATTLE | 1)
p8(E.G_BATTLERS_COUNT, 2)
put(E.G_BATTLER_POSITIONS, bytes((0, 1, 2, 3)))
put(E.G_BATTLER_PARTY_INDEXES, struct.pack("<4H", 0, 0, 0, 0))
p32(E.G_BATTLE_TYPE_FLAGS, 0)
battle_mon(0, TORCHIC, "BLAZE", 12, 30, 34, (10, 10), (SCRATCH, GROWL, EMBER, CUT), (30, 40, 20, 30))
battle_mon(1, TREECKO, "TREECKO", 10, 28, 28, (12, 12), (TACKLE, 0, 0, 0), (35, 0, 0, 0))
p32(E.G_BATTLER_CONTROLLER_FUNCS, E.CHOOSE_ACTION | 1)
p8(E.G_ACTION_CURSOR, 3)                        # (left on RUN last time)
p8(E.G_MOVE_CURSOR, 0)
chosen = []


def battle_tap(b):
    func = g32(E.G_BATTLER_CONTROLLER_FUNCS) & ~1
    cur_a, cur_m = E.G_ACTION_CURSOR, E.G_MOVE_CURSOR
    if func == E.CHOOSE_ACTION:
        c = g8(cur_a)
        if b in ("left", "right"):
            p8(cur_a, c ^ 1 if (b == "right") != bool(c & 1) else c)
        elif b in ("up", "down"):
            p8(cur_a, c ^ 2 if (b == "down") != bool(c & 2) else c)
        elif b == "a":
            chosen.append(("action", g8(cur_a)))
            if g8(cur_a) == 0:
                p32(E.G_BATTLER_CONTROLLER_FUNCS, E.CHOOSE_MOVE | 1)
    elif func == E.CHOOSE_MOVE:                  # (as the game: not right or down onto a place with no move)
        c = g8(cur_m)
        mem = E.Mem(bytes(IW), bytes(EW), bytes(ROM))
        count = sum(1 for k in range(4) if mem.u16(E.G_BATTLE_MONS + 0xC + 2 * k))
        if b == "left" and c & 1 or b == "right" and not c & 1 and c ^ 1 < count:
            p8(cur_m, c ^ 1)
        elif b == "up" and c & 2 or b == "down" and not c & 2 and c ^ 2 < count:
            p8(cur_m, c ^ 2)
        elif b == "a":
            chosen.append(("move", g8(cur_m)))
            p32(E.G_BATTLER_CONTROLLER_FUNCS, 0)


game.on_tap = battle_tap
m = io.snapshot()
check(f"a battle, your turn: {player.mode(m)}", player.mode(m) == ("battle_action", 0))
player.on_battle_action(m, 0)
kind, state, choices, fallback = game.decisions[-1]
for k, v in choices.items():
    print("       ", k, ":", v)
check(f"...the model's choices: each move with its type, power and how it'd do, a switch, running ({fallback} if it "
      f"can't say); MUDDY's fainted, not offered", "super effective" in choices["move2"] and "EMBER" in choices["move2"]
      and "no damage" in choices["move1"] and "run" in choices and not any(k.startswith("switch") for k in choices)
      and fallback == "move2" and state["opponent"]["name"] == "TREECKO" and state["battle"] == "a wild Pokémon")
check(f"...EMBER picked: the cursor from RUN to FIGHT, A, then to the third move, A ({chosen})",
      chosen == [("action", 0), ("move", 2)])

# the battle going on by itself: A now and then for its text, but not on your menu just come up
p32(E.G_BATTLER_CONTROLLER_FUNCS, 0)
waiting = io.snapshot()
game.taps.clear()
player.mode_was, player.since = "battle_wait", Clock.t - 5
player.on_battle_wait(waiting)
tapped_waiting = list(game.taps)
p32(E.G_BATTLER_CONTROLLER_FUNCS, E.CHOOSE_ACTION | 1)     # (the menu's up by the time it taps)
game.taps.clear()
player.since = Clock.t - 5
player.on_battle_wait(waiting)
check(f"a battle going on by itself: A for its text ({tapped_waiting}); not once your menu's up ({game.taps})",
      tapped_waiting == ["a"] and game.taps == [])
p8(E.G_ACTION_CURSOR, 0)

# trainer's battle: no running
p32(E.G_BATTLE_TYPE_FLAGS, E.BATTLE_TRAINER)
p32(E.G_BATTLER_CONTROLLER_FUNCS, E.CHOOSE_ACTION | 1)
player.on_battle_action(io.snapshot(), 0)
check("...a trainer's battle: no running away offered", "run" not in game.decisions[-1][2])
p32(E.G_BATTLER_CONTROLLER_FUNCS, 0)

# a move the game says no to (disabled): the move menu again, that one left out
p32(E.G_BATTLER_CONTROLLER_FUNCS, E.CHOOSE_MOVE | 1)
game.on_tap = battle_tap
player.on_battle_move(io.snapshot(), 0)
check(f"the move menu again after EMBER was refused: EMBER left out ({sorted(game.decisions[-1][2])})",
      "move2" not in game.decisions[-1][2] and "move0" in game.decisions[-1][2])
p32(E.G_BATTLER_CONTROLLER_FUNCS, 0)

# three moves: from the third (bottom-left) to the second (top-right) it's up, then right (the game won't go right
# from the third: there's no fourth)
battle_mon(0, TORCHIC, "BLAZE", 12, 30, 34, (10, 10), (SCRATCH, GROWL, EMBER, 0), (30, 40, 20, 0))
p32(E.G_BATTLER_CONTROLLER_FUNCS, E.CHOOSE_MOVE | 1)
p8(E.G_MOVE_CURSOR, 2)
player.move_tried = None
chosen.clear()
game.taps.clear()
game.picks = ["move1"]
player.on_battle_move(io.snapshot(), 0)
check(f"three moves, the cursor from the third to the second: {game.taps}, {chosen}", chosen == [("move", 1)])
battle_mon(0, TORCHIC, "BLAZE", 12, 30, 34, (10, 10), (SCRATCH, GROWL, EMBER, CUT), (30, 40, 20, 30))
p32(E.G_BATTLER_CONTROLLER_FUNCS, 0)

# switching: POKéMON, then the party menu, the cursor to the one picked, A. MUDDY led (first in the party) and BLAZE
# came in for it (second, out now); the party menu has them in battle order, BLAZE first
BLAZE_MON = (0x1A2B3C4D, 0x55667788, TORCHIC, "BLAZE", 12, 30, 34, (SCRATCH, GROWL, EMBER, CUT), (30, 40, 20, 30))
MUDDY_MON = (0x0BADF00D, 0x55667788, MUDKIP, "MUDDY", 9, 20, 28, (TACKLE, WATER_GUN, 0, 0), (35, 25, 0, 0))
pokemon(0, *MUDDY_MON)
pokemon(1, *BLAZE_MON)
put(E.G_BATTLER_PARTY_INDEXES, struct.pack("<4H", 1, 0, 0, 0))
p32(E.G_BATTLE_TYPE_FLAGS, E.BATTLE_TRAINER)
p32(E.G_BATTLER_CONTROLLER_FUNCS, E.CHOOSE_ACTION | 1)
p8(E.G_ACTION_CURSOR, 0)
chosen.clear()
game.picks = ["switch0"]
player.on_battle_action(io.snapshot(), 0)
check(f"switching to MUDDY: the cursor to POKéMON, A ({chosen}); the plan, by who it is: {player.plan}",
      chosen == [("action", 2)] and player.plan == ("send", 0x0BADF00D))
pokemon(0, *BLAZE_MON)                           # (the menu's up: the party in battle order)
pokemon(1, *MUDDY_MON)
put(E.G_BATTLER_PARTY_INDEXES, struct.pack("<4H", 0, 0, 0, 0))
p32(E.G_MAIN + 4, E.CB2_PARTY_MENU | 1)
p8(E.G_MAIN + 0x439, 2)
put(E.G_PARTY_MENU + 9, bytes((0,)))


def party_tap(b):
    c = E.G_PARTY_MENU + 9
    if b == "down":
        p8(c, (g8(c) + 1) % 2)
    elif b == "up":
        p8(c, (g8(c) - 1) % 2)
    elif b == "a":
        chosen.append(("slot", g8(c)))


game.on_tap = party_tap
chosen.clear()
m = io.snapshot()
check(f"...the party menu: {player.mode(m)}", player.mode(m) == ("party_menu",))
player.on_party_menu(m)
check(f"...MUDDY's place in the menu (second there, though first in the party), A ({chosen})",
      chosen == [("slot", 1)] and player.plan is None)
p32(E.G_TASKS, E.TASK_PARTY_SELECTION | 1)
p8(E.G_TASKS + 4, 1)
check(f"...then its little menu: SEND OUT ({player.mode(io.snapshot())})",
      player.mode(io.snapshot()) == ("tap", "a", "Sending a Pokémon out"))
p8(E.G_TASKS + 4, 0)
# one fainted: the party menu, the model picks who goes next
chosen.clear()
player.on_party_menu(io.snapshot())
check(f"...one fainted (no plan): the model's asked who's next ({sorted(game.decisions[-1][2])}), A ({chosen})",
      sorted(game.decisions[-1][2]) == ["slot0", "slot1"] and len(chosen) == 1)
p32(E.G_MAIN + 4, E.CB2_BATTLE | 1)
p8(E.G_MAIN + 0x439, 0)
p32(E.G_BATTLER_CONTROLLER_FUNCS, 0)
p32(E.G_BATTLE_TYPE_FLAGS, 0)

# "Use next Pokémon?" (a battle script's yes or no) and a move to learn
SCRIPT = 0x08109000
put(SCRIPT, bytes((E.OP_YES_NO,)))
p32(E.G_BATTLESCRIPT_CURR_INSTR, SCRIPT)
put(E.G_BATTLE_COMMUNICATION, bytes((1, 1)))
put(E.G_DISPLAYED_STRING_BATTLE, enc("Use next POKéMON?".replace("é", "e")))


def yes_no_tap(b):
    c = E.G_BATTLE_COMMUNICATION + 1
    if b == "up":
        p8(c, 0)
    elif b == "down":
        p8(c, 1)
    elif b == "a":
        chosen.append(("yesno", g8(c)))


game.on_tap = yes_no_tap
chosen.clear()
m = io.snapshot()
check(f"a battle's question: {player.mode(m)}", player.mode(m) == ("battle_question", E.OP_YES_NO))
player.on_battle_question(m, E.OP_YES_NO)
check(f"...asked with its words ({game.decisions[-1][1]['question']!r}), answered yes: cursor up, A ({chosen})",
      game.decisions[-1][1]["question"] == "Use next POKeMON?" and chosen == [("yesno", 0)])

put(SCRIPT, bytes((E.OP_LEARN_MOVE,)))
p16(E.G_MOVE_TO_LEARN, WATER_GUN)
STRUCT = 0x02035000
p32(E.G_BATTLE_STRUCT, STRUCT)
p8(STRUCT + E.EXP_GETTER, 0)
put(E.G_BATTLE_COMMUNICATION, bytes((0, 1)))   # (the learn-move boxes keep their step in gBattleScripting)
p8(E.G_BATTLE_SCRIPTING_LEARN_MOVE, 0)
mode_before = player.mode(io.snapshot())
p8(E.G_BATTLE_SCRIPTING_LEARN_MOVE, 1)
check(f"a move to learn: its yes or no not up yet ({mode_before}), then up ({player.mode(io.snapshot())})",
      mode_before == ("battle_wait",) and player.mode(io.snapshot()) == ("battle_question", E.OP_LEARN_MOVE))
chosen.clear()
game.picks = ["forget1"]
player.on_battle_question(io.snapshot(), E.OP_LEARN_MOVE)
learn = game.decisions[-1][2]
check(f"a move to learn (WATER GUN, for BLAZE): forget which, or not learn it ({list(learn)}); CUT's an HM, kept: "
      f"yes picked ({chosen}), the plan {player.plan}", "skip" in learn and "forget1" in learn and "forget3" not in learn
      and chosen == [("yesno", 0)] and player.plan == ("forget", 1))
SUMMARY = 0x02036000
p32(E.S_MON_SUMMARY_SCREEN, SUMMARY)
p8(SUMMARY + E.SUMMARY_MOVE_CURSOR, 4)
p32(E.G_MAIN + 4, E.CB2_SUMMARY | 1)
p32(E.G_TASKS, E.TASK_REPLACE_MOVE | 1)
p8(E.G_TASKS + 4, 1)


def summary_tap(b):
    c = SUMMARY + E.SUMMARY_MOVE_CURSOR
    if b == "up":
        p8(c, (g8(c) - 1) % 5)
    elif b == "down":
        p8(c, (g8(c) + 1) % 5)
    elif b == "a":
        chosen.append(("forget", g8(c)))


game.on_tap = summary_tap
chosen.clear()
m = io.snapshot()
check(f"...the summary screen, to forget a move: {player.mode(m)}", player.mode(m) == ("forget_move",))
player.on_forget_move(m)
check(f"...the cursor on GROWL (second), A ({chosen})", chosen == [("forget", 1)] and player.plan is None)
p8(E.G_TASKS + 4, 0)

# ---- out walking again: a yes or no, a script's menu, text -------------------------------------------------------------
p32(E.G_MAIN + 4, E.CB2_OVERWORLD | 1)
p32(E.G_TASKS, E.TASK_YES_NO | 1)
p8(E.G_TASKS + 4, 1)
put(E.S_MENU, bytes((0, 0, 0, 0, 1)))
put(E.G_STRING_VAR4, enc("Would you like me to heal your POKeMON?"))


def menu_tap(b):
    c = E.S_MENU + 2
    if b == "up":
        p8(c, max(0, g8(c) - 1))
    elif b == "down":
        p8(c, min(g8(E.S_MENU + 4), g8(c) + 1))
    elif b == "a":
        chosen.append(("menu", g8(c)))


game.on_tap = menu_tap
chosen.clear()
m = io.snapshot()
check(f"a question out walking: {player.mode(m)}", player.mode(m) == ("question",))
game.picks = ["no"]
player.on_question(m)
check(f"...asked with its words, the model's no: cursor down, A ({chosen})",
      "heal your" in game.decisions[-1][1]["question"] and chosen == [("menu", 1)])
p32(E.G_TASKS, E.TASK_MULTICHOICE | 1)
put(E.G_TASKS + 8, struct.pack("<16h", *([0] * 7 + [3] + [0] * 8)))
put(E.S_MENU, bytes((0, 0, 0, 0, 2)))
chosen.clear()
game.picks = ["LEAVE"]
m = io.snapshot()
check(f"a script's menu: {player.mode(m)[0]}", player.mode(m)[0] == "choice")
player.on_choice(m, player.tasks(m)[E.TASK_MULTICHOICE])
check(f"...its choices, by their words ({game.decisions[-1][2]}); LEAVE picked: two down, A ({chosen})",
      game.decisions[-1][2] == {"c0": "HEAL", "c1": "SHOP", "c2": "LEAVE"} and chosen == [("menu", 2)])
put(MC + 0x40, enc("BUY"))
put(MC + 0x50, enc("SELL"))
put(E.S_MENU, bytes((0, 0, 0, 0, 2)))
player.rom = E.Rom(bytes(ROM))                  # (the cartridge's read once: here, it's been changed)
player.on_choice(io.snapshot(), player.tasks(io.snapshot())[E.TASK_MULTICHOICE])
check(f"...a shop's menu: BUY and SELL left out (it can't shop yet: {game.decisions[-1][2]})",
      game.decisions[-1][2] == {"c2": "LEAVE"})
p32(E.G_TASKS, E.TASK_START_MENU | 1)
check(f"the start menu up (opened before it took over): closed ({player.mode(io.snapshot())})",
      player.mode(io.snapshot()) == ("tap", "b", "Closing the menu"))
p8(E.G_TASKS + 4, 0)
p8(E.S_FIELD_MESSAGE_BOX_MODE, 1)
game.taps.clear()
m = io.snapshot()
player.on_text(m)
check(f"text up: read on with A ({player.mode(m)}, {game.taps})", player.mode(m) == ("text",) and game.taps == ["a"])
p8(E.S_FIELD_MESSAGE_BOX_MODE, 0)
p8(E.S_LOCK_FIELD_CONTROLS, 1)
put(E.S_GLOBAL_SCRIPT_CONTEXT, bytes((1, E.SCRIPT_NATIVE, 0, 0)) + struct.pack("<I", E.WAIT_FOR_A_OR_B | 1))
check(f"a message read out and waiting for A (the message box says it's done by then): read on too "
      f"({player.mode(io.snapshot())})", player.mode(io.snapshot()) == ("text",))
put(E.S_GLOBAL_SCRIPT_CONTEXT, bytes(8))
check(f"a script has you (walking you somewhere): wait ({player.mode(io.snapshot())})",
      player.mode(io.snapshot()) == ("wait_then", "a"))
p8(E.S_LOCK_FIELD_CONTROLS, 0)
p32(E.G_MAIN + 4, 0x08123457)
check(f"a screen it doesn't know (a shop's): out of it with B, in a while ({player.mode(io.snapshot())})",
      player.mode(io.snapshot()) == ("wait_then", "b"))
p32(E.G_MAIN + 4, E.CB2_OVERWORLD | 1)

# ---- the goals ------------------------------------------------------------------------------------------------------------
set_flag(E.FLAG_SYS_POKEDEX_GET, False)
m = io.snapshot()
check(f"the goal now: {player.goal(m)[1]}", player.goal(m)[1] == "Littleroot Town, Professor Birch's Lab")
for fl in (E.FLAG_SYS_POKEDEX_GET,):
    set_flag(fl)
check(f"...the Pokédex got: next, your dad ({player.goal(io.snapshot())[1]})",
      player.goal(io.snapshot())[1] == "Petalburg City, Gym")
p16(SB1 + E.SB1_VARS + 2 * (E.VAR_PETALBURG_GYM_STATE - 0x4000), 2)
check(f"...seen him: the Stone Badge ({player.goal(io.snapshot())[1]})",
      player.goal(io.snapshot())[1] == "Rustboro City, Gym")
places = [st_[2].format(you=E.HOUSES[0], rival=E.HOUSES[1]) for st_ in E.STORY]
check(f"every step's map is one of the game's ({[p_ for p_ in places if p_ not in player.rom.by_name]})",
      all(p_ in player.rom.by_name for p_ in places))
check(f"the game's text read: {E.text(enc('Hello, world!') + bytes((0xFC, 1, 2)) + enc('A'))!r}",
      E.text(enc("Hello, world!")) == "Hello, world!")
icons = bytes((ENC["A"], 0xF8, 0x05, ENC["B"], 0xF9, 0x02, ENC["C"], 0xF7, 0x01, 0xFF))
check(f"...a button's picture or a symbol in it, left out with its number ({E.text(icons)!r})", E.text(icons) == "ABC")
juan = next(st_ for st_ in E.STORY if "Rain Badge" in st_[1])
check(f"the eighth badge is Juan's ({juan[1][-40:]!r})", "Juan" in juan[1] and "Wallace" not in juan[1]
      and juan[3] == E.SCR_JUAN)

# ---- the story, step by step, from its flags and vars ------------------------------------------------------------------
def setvar(var, v):
    p16(SB1 + E.SB1_VARS + 2 * (var - 0x4000), v)


STORY_FLAGS = (E.FLAG_SYS_POKEMON_GET, E.FLAG_DEFEATED_RIVAL_ROUTE103, E.FLAG_SYS_POKEDEX_GET, E.FLAG_BADGE[0])
STORY_VARS = (E.VAR_LITTLEROOT_INTRO_STATE, E.VAR_LITTLEROOT_RIVAL_STATE, E.VAR_LITTLEROOT_TOWN_STATE,
              E.VAR_ROUTE101_STATE, E.VAR_BIRCH_LAB_STATE, E.VAR_PETALBURG_GYM_STATE)


def story(girl=False, flags=(), **vars_):
    for fl in STORY_FLAGS:
        set_flag(fl, fl in flags)
    for v in STORY_VARS:
        setvar(v, 0)
    for name, v in vars_.items():
        setvar(getattr(E, "VAR_" + name.upper()), v)
    p8(SB2 + E.SB2_GENDER, 1 if girl else 0)
    return E.story_step(io.snapshot())


setvar(E.VAR_LITTLEROOT_INTRO_STATE, 6)
check(f"the game's vars read ({E.Mem(bytes(IW), bytes(EW), bytes(ROM)).var(E.VAR_LITTLEROOT_INTRO_STATE)}), and "
      f"whether you're a boy", E.Mem(bytes(IW), bytes(EW), bytes(ROM)).var(E.VAR_LITTLEROOT_INTRO_STATE) == 6
      and E.Mem(bytes(IW), bytes(EW), bytes(ROM)).male())
steps = [("a new game: in the truck", story(), "Littleroot Town", None),
         ("in your house: the clock (a boy's room, Brendan's house)", story(littleroot_intro_state=4),
          "Littleroot Town, Brendan's House 2F", E.SCR_WALL_CLOCK[0]),
         ("...a girl's (May's house)", story(girl=True, littleroot_intro_state=5), "Littleroot Town, May's House 2F",
          E.SCR_WALL_CLOCK[1]),
         ("the clock set: the TV downstairs", story(littleroot_intro_state=6), "Littleroot Town, Brendan's House 1F",
          None),
         ("then your rival next door (a boy's rival: May's house)", story(littleroot_intro_state=7),
          "Littleroot Town, May's House 2F", E.SCR_RIVALS_POKE_BALL[0]),
         ("...a girl's (Brendan's house)", story(girl=True, littleroot_intro_state=7),
          "Littleroot Town, Brendan's House 2F", E.SCR_RIVALS_POKE_BALL[1]),
         ("met: north to Route 101", story(littleroot_intro_state=7, littleroot_rival_state=3,
                                            littleroot_town_state=1), "Route 101", None),
         ("Professor Birch chased: his bag", story(littleroot_intro_state=7, littleroot_town_state=2,
                                                   route101_state=2), "Route 101", E.SCR_BIRCHS_BAG),
         ("your first Pokémon: your rival on Route 103", story(flags=(E.FLAG_SYS_POKEMON_GET,), birch_lab_state=3),
          "Route 103", E.SCR_ROUTE103_RIVAL),
         ("then the Pokédex", story(flags=(E.FLAG_SYS_POKEMON_GET, E.FLAG_DEFEATED_RIVAL_ROUTE103)),
          "Littleroot Town, Professor Birch's Lab", E.SCR_BIRCH),
         ("then your dad", story(flags=STORY_FLAGS[:3]), "Petalburg City, Gym", E.SCR_NORMAN),
         ("then Roxanne", story(flags=STORY_FLAGS[:3], petalburg_gym_state=2), "Rustboro City, Gym", E.SCR_ROXANNE)]
for what, got, place, script in steps:
    check(f"the story's next step, {what}: {got['place']} ({got['words'][:44]}...)", got["place"] == place
          and got["script"] == script)
check(f"...and how strong your team should be for Roxanne (level {steps[-1][1]['level']})", steps[-1][1]["level"] == 13)

# ---- your room: the clock on the wall, looked at (no one to talk to: a thing on the wall) -------------------------------
game.on_tap = None                            # (out walking again: the game's own buttons)
story(littleroot_intro_state=4)
game.warp(BEDROOM, 12, 11)
asked, game.taps[:] = len(game.decisions), []
m = io.snapshot()
f = E.Field(m, player.rom)
check(f"your room: the clock on its wall, something to look at ({[(x, y) for x, y, *_ in f.signs]})",
      [(x, y, d) for x, y, d, _ in f.signs] == [(12, 8, 0)])
player.on_walk(m)
check(f"...the story's next step: walked up to it ({game.me()}), facing it, A ({game.talks[-1:]}); the model not "
      f"asked ({walked().get('by')})", game.me() == (12, 9) and game.facing() == E.NORTH
      and game.talks[-1:] == [(12, 8)] and game.taps[-1] == "a" and len(game.decisions) == asked
      and walked().get("by") == "story")

# ---- Route 101: Professor Birch's bag -----------------------------------------------------------------------------------
story(littleroot_intro_state=7, littleroot_rival_state=3, littleroot_town_state=2, route101_state=2)
game.warp(ROUTE101, 10, 12)
for i, (lid, gfx, x, y, tr) in enumerate(((1, 5, 14, 12, 1), (2, E.GFX_ITEM_BALL, 8, 10, 0), (3, 10, 15, 15, 0),
                                          (5, 97, 9, 16, 0)), 1):
    put_object(i, lid, gfx, x, y, trainer=tr)
asked = len(game.decisions)
player.on_walk(io.snapshot())
check(f"Route 101, Professor Birch chased: to his bag, not the people or the door ({walked().get('words')!r}), "
      f"A facing it ({game.talks[-1:]})", game.talks[-1:] == [(9, 16)] and len(game.decisions) == asked
      and walked().get("pick") == "story")

# ---- badly hurt: to the nurse first ---------------------------------------------------------------------------------
story(flags=STORY_FLAGS[:3], petalburg_gym_state=2)
game.warp(ROUTE101, 10, 12)
for i, (lid, gfx, x, y, tr) in enumerate(((1, 5, 14, 12, 1), (6, E.GFX_NURSE, 14, 15, 0)), 1):
    put_object(i, lid, gfx, x, y, trainer=tr)
pokemon(0, 0x1A2B3C4D, 0x55667788, TORCHIC, "BLAZE", 12, 3, 34, (SCRATCH, GROWL, EMBER, CUT), (30, 40, 20, 30))
pokemon(1, 0x0BADF00D, 0x55667788, MUDKIP, "MUDDY", 9, 0, 28, (TACKLE, WATER_GUN, 0, 0), (35, 25, 0, 0))
asked = len(game.decisions)
player.on_walk(io.snapshot())
check(f"badly hurt: to the nurse, without asking ({walked().get('by')}, talked to {game.talks[-1:]})",
      game.talks[-1:] == [(14, 15)] and len(game.decisions) == asked and walked().get("by") == "heal")

# ---- too weak for Roxanne: training in the grass ------------------------------------------------------------------------
pokemon(0, 0x1A2B3C4D, 0x55667788, TORCHIC, "BLAZE", 12, 34, 34, (SCRATCH, GROWL, EMBER, CUT), (30, 40, 20, 30))
game.warp(ROUTE101, 10, 12)
E.GRASS_STEPS = 4
asked, game.steps = len(game.decisions), 0
st = player.state(io.snapshot())
player.on_walk(io.snapshot())
E.GRASS_STEPS = 40
check(f"your best Pokémon level 12, Roxanne's wants 13: told to train ({st.get('note')!r}), and off to the grass, "
      f"without asking ({walked().get('by')}, {game.steps} steps)", "train" in st.get("note", "")
      and walked().get("by") == "train" and walked().get("pick") == "grass" and len(game.decisions) == asked
      and game.steps >= 4)
check(f"the cartridge's maps: which have tall grass (Route 101: {player.rom.grassy(ROUTE101)}, the Lab: "
      f"{player.rom.grassy(LAB)})", player.rom.grassy(ROUTE101) and not player.rom.grassy(LAB))

# ---- what people said, told to the model ----------------------------------------------------------------------------
p8(E.S_FIELD_MESSAGE_BOX_MODE, 1)
for words_ in ("Hi! You must be new here.", "My kid went out to Route 101."):
    put(E.G_STRING_VAR4, enc(words_))
    player.on_text(io.snapshot())
    player.on_text(io.snapshot())
p8(E.S_FIELD_MESSAGE_BOX_MODE, 0)
said = player.state(io.snapshot()).get("people said, lately")
check(f"what people said, the last few, once each: {said}", said[-2:] == ["Hi! You must be new here.",
                                                                           "My kid went out to Route 101."])

# ---- screens of its own: the title, the main menu, the clock, the first Pokémon ---------------------------------------
def task(func, data=(), slot=0):
    p32(E.G_TASKS + E.TASK_SIZE * slot, func | 1)
    p8(E.G_TASKS + E.TASK_SIZE * slot + 4, 1)
    put(E.G_TASKS + E.TASK_SIZE * slot + 8, struct.pack("<16h", *(list(data) + [0] * (16 - len(data)))))


def no_tasks():
    for k in range(E.TASKS):
        p8(E.G_TASKS + E.TASK_SIZE * k + 4, 0)


no_tasks()
p32(E.G_MAIN + 4, E.CB2_TITLE | 1)
title_mode = player.mode(io.snapshot())
p32(E.G_MAIN + 4, E.CB2_MAIN_MENU | 1)
menu_mode = player.mode(io.snapshot())
check(f"the title screen: START ({title_mode}); the main menu, and Professor Birch's talk for a new game: A "
      f"({menu_mode})", title_mode[:2] == ("tap", "start") and menu_mode[:2] == ("tap", "a"))
p32(E.G_MAIN + 4, E.CB2_WALL_CLOCK | 1)
task(E.TASK_SET_CLOCK)
set_mode = player.mode(io.snapshot())
task(E.TASK_CONFIRM_CLOCK)
put(E.S_MENU, bytes((0, 0, 1, 0, 1)))             # (its YES / NO: on NO to start with)
game.on_tap, chosen[:] = menu_tap, []
m = io.snapshot()
confirm_mode = player.mode(m)
player.on_yes(m, "Setting the clock")
check(f"the clock: the time as it is, A ({set_mode}); then YES, which isn't where its cursor starts ({confirm_mode}, "
      f"{chosen})", set_mode[:2] == ("tap", "a") and confirm_mode[0] == "yes" and chosen == [("menu", 0)])
task(E.TASK_VIEW_CLOCK)
check(f"...looked at later: B ({player.mode(io.snapshot())})", player.mode(io.snapshot())[:2] == ("tap", "b"))
p32(E.G_MAIN + 4, E.CB2_STARTER | 1)
task(E.TASK_CHOOSE_STARTER, (1,))


def starter_tap(b):
    a = E.G_TASKS + 8
    sel = struct.unpack("<h", bytes(EW[0:0]) or E.Mem(bytes(IW), bytes(EW), bytes(ROM)).bytes(a, 2))[0]
    if b == "right" and sel < 2:
        put(a, struct.pack("<h", sel + 1))
    elif b == "left" and sel > 0:
        put(a, struct.pack("<h", sel - 1))
    elif b == "a":
        chosen.append(("starter", sel))


game.on_tap, chosen[:] = starter_tap, []
asked = len(game.decisions)
game.picks = ["mudkip"]
for _ in range(4):
    m = io.snapshot()
    md = player.mode(m)
    if md[0] != "starter" or chosen:
        break
    player.on_starter(m, md[1])
check(f"Professor Birch's bag: the model picks your first Pokémon, once ({list(game.decisions[-1][2])}); the cursor "
      f"from Torchic to Mudkip, A ({chosen})", len(game.decisions) == asked + 1 and game.decisions[-1][0] == "starter"
      and list(game.decisions[-1][2]) == ["treecko", "torchic", "mudkip"] and chosen == [("starter", 2)])
task(E.TASK_CONFIRM_STARTER)
check(f"...then its YES ({player.mode(io.snapshot())})", player.mode(io.snapshot())[0] == "yes")
no_tasks()
p32(E.G_MAIN + 4, E.CB2_OVERWORLD | 1)

# ---- the way round: Route 104's two parts, through Petalburg Woods ------------------------------------------------
story(flags=STORY_FLAGS[:3], petalburg_gym_state=2)       # (to Roxanne, at the Rustboro City Gym)
pokemon(0, 0x1A2B3C4D, 0x55667788, TORCHIC, "BLAZE", 20, 60, 60, (SCRATCH, GROWL, EMBER, CUT), (30, 40, 20, 30))
p8(E.G_PLAYER_PARTY_COUNT, 1)
for i in range(1, 6):
    p32(E.G_OBJECT_EVENTS + E.OBJECT_EVENT_SIZE * i, 0)
game.warp(R104, 12, 15)                                  # (Route 104's south part)


def where_to():
    m_ = io.snapshot()
    f_ = E.Field(m_, player.rom)
    step_ = player.step(m_)
    team_ = E.party(m_, player.rom)
    opts_ = player.options(m_, f_, step_, team_)
    return f_, opts_, player.sure(f_, opts_, step_, team_)


f, opts, (pick, why) = where_to()
check(f"Route 104's south part: the road north to Rustboro can't be walked to ({'road2' in opts}); the door into the "
      f"woods is a way round ({opts.get('door0', {}).get('words')!r}): taken ({pick}, {why})",
      "road2" not in opts and opts["door0"].get("around") and pick == "door0" and why == "story")
player.taken[(R104, ("door", 9, 13))] = 1
game.warp(WOODS, 8, 14)                                  # (in the woods, by the door it came in at)
player.came_in[WOODS] = (8, 14)                         # (as on_walk notes, arriving)
f, opts, (pick, why) = where_to()
check(f"...in the woods: both ways out go to Route 104 ({opts['door0']['words']!r}, {opts['door1']['words']!r}); not "
      f"back the way it came in, but the other ({pick})", opts["door0"]["toward"] and opts["door1"]["toward"]
      and pick == "door1")
game.warp(R104, 12, 9)                                  # (out on the north part)
f, opts, (pick, why) = where_to()
check(f"...out on Route 104's north part: the road north, to Rustboro ({pick}: {opts.get(pick, {}).get('words')!r})",
      pick == "road2")
set_flag(E.FLAG_BADGE[0])
setvar(E.VAR_RUSTBORO_CITY_STATE, 1)
st_ = E.story_step(io.snapshot())
check(f"Roxanne beaten: walk west from the Gym, where the Devon Goods get stolen ({st_['place']}, {st_['script']})",
      st_["place"] == "Rustboro City" and st_["script"] == ("tile", 23, 22))
game.warp(RUSTBORO, 12, 15)
m_ = io.snapshot()
f_ = E.Field(m_, player.rom)
spot = player.options(m_, f_, dict(st_, script=("tile", 3, 3)), E.party(m_, player.rom)).get("story", {})
check(f"...a place to walk to, in the story: offered ({spot.get('words')!r}), to (10, 10)",
      spot.get("kind") == "spot" and spot.get("target") == (10, 10))
setvar(E.VAR_RUSTBORO_CITY_STATE, 2)
check(f"...stolen: after them, to Rusturf Tunnel ({E.story_step(io.snapshot())['place']})",
      E.story_step(io.snapshot())["place"] == "Rusturf Tunnel")
setvar(E.VAR_RUSTBORO_CITY_STATE, 0)
set_flag(E.FLAG_BADGE[0], False)
player.came_in.clear()
player.taken.clear()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
