"""Pokémon Emerald (the US game), played by a decision model on your bot's computer (pitato/gameai.py runs this
while the game plays). Everything comes from the game's own memory as it plays: where you are and what's around
you (the map's tiles, its doors and roads, its people and the things you can look at), your Pokémon, a battle, the
text on the screen and the menu that's up, and how far the story's got (its flags and vars). It knows the story:
the next thing to do (get out of the truck, set the clock, meet your rival, save Professor Birch, and on, badge by
badge), where (the map, and who or what to see there), and how strong your team should be first; it walks there by
itself, the shortest way it knows, healing when your team's badly hurt and training in tall grass when it's too
weak for the next Gym. The model's asked at each moment that needs a decision (a battle's next move, a yes or no,
which Pokémon to start with, where to go when the way isn't known), from a short description and a few choices,
with what people just said; the rest (the title screen, text, menus, the clock, walking a path) this does itself,
a button at a time, watching the game as it goes. Addresses and layouts are from pret's decompilation of the game
(github.com/pret/pokeemerald)."""
import json
import random
import struct
import time
from collections import deque

from .emerald_maps import MAP_NAMES

# ---- the game ---------------------------------------------------------------------------------------------------
GAME_CODE, GAME_VERSION = b"BPEE", 0          # the cartridge's code (at 0xAC) and version (0xBC): Emerald, English
ROM_BASE, EWRAM, IWRAM = 0x08000000, 0x02000000, 0x03000000
EWRAM_SIZE, IWRAM_SIZE = 0x40000, 0x8000

# working memory (pokeemerald.sym)
G_MAIN = 0x030022C0                            # struct Main: callback2 at +4, inBattle (bit 1) at +0x439
G_TASKS, TASK_SIZE, TASKS = 0x03005E00, 40, 16
G_SAVEBLOCK1_PTR, G_SAVEBLOCK2_PTR = 0x03005D8C, 0x03005D90
G_PLAYER_PARTY, G_PLAYER_PARTY_COUNT = 0x020244EC, 0x020244E9
G_BATTLE_MONS, BATTLE_MON_SIZE = 0x02024084, 0x58
G_BATTLE_TYPE_FLAGS = 0x02022FEC
G_BATTLERS_COUNT = 0x0202406C
G_BATTLER_POSITIONS = 0x02024076
G_BATTLER_PARTY_INDEXES = 0x0202406E
G_BATTLER_CONTROLLER_FUNCS = 0x03005D60
G_ACTION_CURSOR, G_MOVE_CURSOR = 0x020244AC, 0x020244B0
G_BATTLE_COMMUNICATION = 0x02024332          # [0] a battle script's step, [1] a yes/no box's cursor
G_BATTLE_SCRIPTING_LEARN_MOVE = 0x02024474 + 0x1F   # gBattleScripting.learnMoveState: the learn-move boxes' step
S_GLOBAL_SCRIPT_CONTEXT = 0x03000E40         # the script running out walking: mode at +1, nativePtr at +4
SCRIPT_NATIVE = 2                            # ...the mode while it waits on a function of the game's
WAIT_FOR_A_OR_B = 0x0809AC98                 # ...this one: a message that's been read out, waiting for A
G_BATTLESCRIPT_CURR_INSTR = 0x02024214
G_DISPLAYED_STRING_BATTLE = 0x02022E2C       # a battle's text
G_MULTI_USE_PLAYER_CURSOR = 0x03005D74       # "Will you switch?" box's cursor
G_MOVE_TO_LEARN = 0x020244E2
G_BATTLE_STRUCT = 0x0202449C                 # pointer; expGetterMonId (who's learning a move) at +0x10
EXP_GETTER = 0x10
G_MAP_HEADER = 0x02037318                    # the map you're on (struct MapHeader, a copy)
G_BACKUP_MAP_LAYOUT = 0x03005DC0             # its tiles, with the roads around: width, height, pointer
G_OBJECT_EVENTS, OBJECT_EVENT_SIZE, OBJECT_EVENTS = 0x02037350, 0x24, 16
G_PLAYER_AVATAR = 0x02037590                 # flags at +0, a step under way at +3 (not 0), your object's number +5
S_FIELD_MESSAGE_BOX_MODE = 0x020375BC        # a message is being read out (not 0)
S_LOCK_FIELD_CONTROLS = 0x03000F2C           # a script has you (not 0)
S_MENU = 0x0203CD90                          # menu.c's menu: cursorPos at +2, min +3, max +4
G_STRING_VAR4 = 0x02021FC4                   # the text a message or question shows
G_PALETTE_FADE = 0x02037FD4                  # active: bit 7 of byte 7
G_PARTY_MENU = 0x0203CEC8                    # slotId at +9
S_MON_SUMMARY_SCREEN = 0x0203CF1C            # pointer; the move cursor (firstMoveIndex) at +0x40C6
SUMMARY_MOVE_CURSOR = 0x40C6

# the game's code: what's running (a callback or a task, compared with its address)
CB2_OVERWORLD = 0x08085E5C
CB2_BATTLE = 0x08038420                      # BattleMainCB2
CB2_PARTY_MENU = 0x081B01B0
CB2_NAMING_SCREEN = 0x080E4F58
CB2_EVOLUTION = (0x0813E3A4, 0x0813E3C0)
CB2_SUMMARY = 0x081BFAB4
CB2_BAG = 0x081AAD5C
CHOOSE_ACTION, CHOOSE_MOVE, CHOOSE_TARGET = 0x08057588, 0x08057BFC, 0x08057824
SWITCH_YES_NO = 0x080599D4                   # PlayerHandleYesNoInput: "Will you change Pokémon?"
TASK_YES_NO, TASK_MULTICHOICE = 0x080E215C, 0x080E2058
TASK_PARTY_SELECTION = 0x081B3730            # the party menu's little SHIFT / SUMMARY / CANCEL menu
TASK_REPLACE_MOVE = 0x081C174C               # the summary screen, picking a move to forget
TASK_START_MENU = 0x0809FA34                 # Task_ShowStartMenu (the menu up)
CB2_TITLE = 0x080AAB2C                       # the title screen (title_screen.c's MainCB2)
CB2_MAIN_MENU = 0x0802F6B0                   # the main menu (CONTINUE, NEW GAME...), and Professor Birch's talk before
                                             # a new game (boy or girl, your name: A takes what's offered)
CB2_WALL_CLOCK = 0x08134C9C                  # your room's clock, being set (or looked at)
TASK_SET_CLOCK, TASK_CONFIRM_CLOCK, TASK_VIEW_CLOCK = 0x08134CE8, 0x08134E30, 0x08134F40
CB2_STARTER = 0x081341E0                     # Professor Birch's bag: your first Pokémon picked
TASK_CHOOSE_STARTER, TASK_CONFIRM_STARTER = 0x0813425C, 0x08134400
STARTERS = (("treecko", "Treecko (Grass type)"), ("torchic", "Torchic (Fire type)"),
            ("mudkip", "Mudkip (Water type, later Water and Ground)"))

# the cartridge's tables
SPECIES_NAMES, SPECIES_NAME_LEN, SPECIES_COUNT = 0x083185C8, 11, 412
MOVE_NAMES, MOVE_NAME_LEN, MOVES_COUNT = 0x0831977C, 13, 355
BATTLE_MOVES, BATTLE_MOVE_SIZE = 0x0831C898, 12
TYPE_EFFECTIVENESS, TYPE_NAMES, TYPE_NAME_LEN = 0x0831ACE8, 0x0831AE38, 7
SPECIES_INFO, SPECIES_INFO_SIZE = 0x083203CC, 28
MAP_GROUPS = 0x08486578
REGION_MAP_ENTRIES, MAPSEC_COUNT = 0x085A147C, 213
MULTICHOICE_LISTS, MULTICHOICES = 0x0858B760, 114

# battle scripts' commands that wait on a yes or no
OP_YES_NO, OP_LEARN_MOVE, OP_STOP_LEARNING, OP_NICKNAME = 0x67, 0x5A, 0x5B, 0xF3
# battle types
BATTLE_DOUBLE, BATTLE_TRAINER, BATTLE_SAFARI = 1 << 0, 1 << 3, 1 << 7

# save block 1
SB1_POS, SB1_LOCATION, SB1_DYNAMIC_WARP, SB1_MONEY, SB1_FLAGS, SB1_VARS = 0x00, 0x04, 0x14, 0x490, 0x1270, 0x139C
SB2_GENDER, SB2_ENCRYPTION_KEY = 0x08, 0xAC
VARS_START = 0x4000

# the story's own progress, early on (include/constants/vars.h)
VAR_LITTLEROOT_TOWN_STATE = 0x4050           # 1 met your rival, 2 off to save Birch, 3 the Pokédex
VAR_RUSTBORO_CITY_STATE = 0x405A             # 1 Roxanne beaten, 2 the Devon Goods stolen
VAR_ROUTE101_STATE = 0x4060                  # 2 Birch being chased
VAR_BIRCH_LAB_STATE = 0x4084                 # 3 told to see your rival, 4 back for the Pokédex
VAR_PETALBURG_GYM_STATE = 0x4085             # 2 and up: your dad's seen you (and Wally caught his first Pokémon)
VAR_LITTLEROOT_RIVAL_STATE = 0x408D          # 3 met your rival
VAR_LITTLEROOT_INTRO_STATE = 0x4092          # 3 in your house, 6 the clock set, 7 the TV seen

# flags
TRAINER_FLAGS_START = 0x500
FLAG_SYS_POKEMON_GET, FLAG_SYS_POKEDEX_GET, FLAG_SYS_GAME_CLEAR = 0x860, 0x861, 0x864
FLAG_BADGE = tuple(0x867 + i for i in range(8))
FLAG_DEFEATED_RIVAL_ROUTE103, FLAG_RECOVERED_DEVON_GOODS, FLAG_DELIVERED_DEVON_GOODS = 0x82, 0x8F, 0x95
FLAG_RECEIVED_POKENAV, FLAG_DELIVERED_STEVEN_LETTER = 0xBC, 0xBD
FLAG_DEFEATED_EVIL_TEAM_MT_CHIMNEY, FLAG_RECEIVED_HM_SURF = 0x8B, 0x7A
FLAG_VISITED_DEWFORD_TOWN, FLAG_VISITED_SLATEPORT_CITY = 0x871, 0x877

# the story's people and things, by their scripts (pokeemerald.sym): (a boy's, a girl's) where it's your house or your
# rival's
SCR_WALL_CLOCK = (0x08292781, 0x0829278D)    # your room's clock (Brendan's house, May's)
SCR_RIVALS_POKE_BALL = (0x081F9334, 0x081F8481)   # the Poké Ball in your rival's room (May's house, Brendan's)
SCR_BIRCHS_BAG, SCR_BIRCH, SCR_ROUTE103_RIVAL = 0x081EBE16, 0x081FA25A, 0x081EC3C1
SCR_NORMAN, SCR_ROXANNE, SCR_RUSTURF_GRUNT, SCR_MR_STONE = 0x082049F1, 0x08212F31, 0x0822D0C2, 0x0821256C
SCR_BRINEY_HOUSE, SCR_DEWFORD_BRINEY, SCR_BRAWLY, SCR_STEVEN = 0x08229D67, 0x081E9511, 0x081FC7C2, 0x0822DC7B
SCR_STERN, SCR_WATTSON, SCR_MAXIE, SCR_FLANNERY = 0x0820BB00, 0x0820DEEB, 0x0822EE0B, 0x081FE78C
SCR_WALLYS_DAD, SCR_WINONA, SCR_TATE_LIZA, SCR_JUAN = 0x08204278, 0x082165C8, 0x08220898, 0x08224F44
HOUSES = ("Littleroot Town, Brendan's House", "Littleroot Town, May's House")   # a boy's, a girl's
LAB = "Littleroot Town, Professor Birch's Lab"

# the map's tiles
MAP_OFFSET = 7                                # the map's own tiles start this far in, with the roads around
BLOCK_UNDEFINED = 0x3FF
MB_TALL_GRASS, MB_LONG_GRASS = 2, 3
MB_COUNTER = 128
MB_ANIMATED_DOOR = 105
MB_ARROW_WARP = {98: 4, 99: 3, 100: 2, 101: 1, 109: 1, 28: 1, 27: 2}   # an exit you stand on, then walk this way
MB_JUMP = {56: 4, 57: 3, 58: 2, 59: 1}       # a ledge: you jump it going this way
MB_SURFABLE = {16, 17, 18, 20, 21, 80, 81, 82, 83}   # water that Surf starts from (A, facing it)
LAND, WATER = 3, 1                           # the heights of land and of water you surf on
BLOCKED_GOING = {1: {51, 54, 55, 192}, 2: {50, 52, 53, 192}, 3: {49, 53, 55, 193, 190}, 4: {48, 52, 54, 193, 190}}
BLOCKED_COMING = {1: BLOCKED_GOING[2], 2: BLOCKED_GOING[1], 3: BLOCKED_GOING[4], 4: BLOCKED_GOING[3]}
# directions as the game numbers them
SOUTH, NORTH, WEST, EAST = 1, 2, 3, 4
STEP = {SOUTH: (0, 1), NORTH: (0, -1), WEST: (-1, 0), EAST: (1, 0)}
BUTTON = {SOUTH: "down", NORTH: "up", WEST: "left", EAST: "right"}
WORD = {SOUTH: "south", NORTH: "north", WEST: "west", EAST: "east"}
CONNECTION_DIRS = {1: SOUTH, 2: NORTH, 3: WEST, 4: EAST}
# objects
GFX_NURSE, GFX_ITEM_BALL, GFX_CUT_TREE, GFX_ROCK, GFX_BOULDER = 58, 59, 82, 86, 87
SCR_OP_TRAINERBATTLE = 0x5C
AVATAR_SURFING = 1 << 3
OPPOSITE = {SOUTH: NORTH, NORTH: SOUTH, WEST: EAST, EAST: WEST}
GRASS = (MB_TALL_GRASS, MB_LONG_GRASS)
# moves
MOVE_CUT, MOVE_SURF, MOVE_ROCK_SMASH = 15, 57, 249
HM_MOVES = {15, 19, 57, 70, 127, 148, 249, 291}   # Cut, Fly, Surf, Strength, Waterfall, Flash, Rock Smash, Dive:
                                                  # the game won't let them be forgotten

# types (Gen 3: the type decides physical or special)
TYPES = ("Normal", "Fighting", "Flying", "Poison", "Ground", "Rock", "Bug", "Ghost", "Steel", "???",
         "Fire", "Water", "Grass", "Electric", "Psychic", "Ice", "Dragon", "Dark")
SPECIAL_TYPES = {10, 11, 12, 13, 14, 15, 16, 17}
STATUS_WORDS = ((0x7, "asleep"), (0x8, "poisoned"), (0x10, "burned"), (0x20, "frozen"), (0x40, "paralyzed"),
                (0x80, "badly poisoned"))
# where the four parts of a Pokémon's data are, by its personality (pokemon.c's SUBSTRUCT_CASE): growth, moves
SUBSTRUCT_POS = ((0, 1), (0, 1), (0, 2), (0, 3), (0, 2), (0, 3), (1, 0), (1, 0), (2, 0), (3, 0), (2, 0), (3, 0),
                 (1, 2), (1, 3), (2, 1), (3, 1), (2, 3), (3, 2), (1, 2), (1, 3), (2, 1), (3, 1), (2, 3), (3, 2))

# the game's letters
CHARS = {0x00: " ", 0x1B: "é", 0x2D: "&", 0x2E: "+", 0x35: "=", 0x36: ";", 0x5B: "%", 0x5C: "(", 0x5D: ")",
         0x53: "PK", 0x54: "MN", 0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-", 0xB0: "...", 0xB1: '"', 0xB2: '"',
         0xB3: "'", 0xB4: "'", 0xB5: "♂", 0xB6: "♀", 0xB8: ",", 0xB9: "x", 0xBA: "/", 0xF0: ":"}
CHARS.update({0xA1 + i: str(i) for i in range(10)})
CHARS.update({0xBB + i: chr(ord("A") + i) for i in range(26)})
CHARS.update({0xD5 + i: chr(ord("a") + i) for i in range(26)})
CTRL_LENGTHS = (1, 2, 2, 2, 4, 2, 2, 1, 2, 1, 1, 3, 2, 2, 2, 1, 3, 2, 2, 2, 2, 1, 1, 1, 1)

# how it plays
TEXT_EVERY = 0.25            # seconds between A presses through text
WAIT_EVERY = 0.12            # seconds between looks while nothing's for it to do
STUCK_AFTER = 8.0            # seconds of a script or a screen it doesn't know, then it tries a button
STEP_TIME = 0.9              # seconds a step may take (a turn, then the step), or it was blocked
WARP_TIME = 4.0              # seconds for a door, a road or stairs to take you somewhere else
GRASS_STEPS = 40             # steps back and forth in tall grass, looking for a wild Pokémon
TALK_TRIES = 3               # tries to get next to someone who moves about
RECENT = 8                   # things it's done, told to the model so it doesn't go round in circles
NEAREST_PEOPLE = 6           # people and items offered at once, the nearest
PICK_TIMEOUT = 30.0          # seconds the model has to pick (the first time longer: pitato/gameai.py)
SAME_PICK = (3, 8)           # picked this many times in the last so many, here: not offered for a while (going round
                             # in circles)
CANT_DO = {"BUY", "SELL"}    # a menu's choices that open screens it can't use yet (a shop's)
ERRORS_MOST = 40             # looks in a row that didn't make sense (memory caught mid-change): then it stops
HEAL_AT = 0.6                # your team this hurt (of its HP, all told): off to heal
SAID = 4                     # things people said lately, told to the model
TRIED_FOR = 120.0            # seconds something that didn't work isn't offered again, where it didn't
BG_FACING = {1: NORTH, 2: SOUTH, 3: EAST, 4: WEST}   # a thing to look at that's seen facing only one way (else any)

SAYS_WALK = ("You are playing Pokémon Emerald. Pick what to do next. Work toward the goal; heal at a "
             "Pokémon Center when your Pokémon are badly hurt; battle wild Pokémon and trainers to get stronger "
             "when the next challenge looks too hard; talk to people, they help the story on; don't keep doing "
             "the same thing over and over.")
SAYS_BATTLE = ("You are in a Pokémon battle in Pokémon Emerald. Pick the best action: a move that does a lot of "
               "damage (super effective, strong, same type as the user), or switch to a healthier Pokémon with a "
               "type advantage. In a wild battle you may run if it's going badly.")
SAYS_ANSWER = ("You are playing Pokémon Emerald and the game asks a question. Answer the way that helps you "
               "progress: yes to healing, to gifts, and to what moves the story on; no to giving nicknames.")
SAYS_LEARN = ("In Pokémon Emerald, your Pokémon can learn a new move but already knows four. Keep the best four: "
              "strong, accurate attacks of different types (one matching its own type is best).")
SAYS_STARTER = ("You are starting Pokémon Emerald and picking your first Pokémon, your partner for the whole game. "
                "Pick the one that makes the game easiest: the first Gyms are Rock, Fighting, Electric and Fire "
                "types.")


def flagged(flag):
    return lambda m: m.flag(flag)


def begun(m):
    """You've your first Pokémon: the story's past its start (a save from later on)."""
    return m.flag(FLAG_SYS_POKEMON_GET)


# the story, step by step: (done, what to do, where (a map's name: {you} your house, {rival} your rival's), who or
# what to see there (its script: one, or a boy's and a girl's; or ("tile", x, y): a place to walk to, where something
# happens), what that's called, how strong your team should be first (its best Pokémon's level: a little under the
# Gym Leader's best)). The next step's the first that isn't done.
STORY = (
    (lambda m: m.var(VAR_LITTLEROOT_INTRO_STATE) >= 3 or begun(m),
     "Get out of the moving truck: walk out of its open back, on the right.", "Littleroot Town", None, "", None),
    (lambda m: m.var(VAR_LITTLEROOT_INTRO_STATE) >= 6 or begun(m),
     "Go upstairs to your room and set the clock on the wall.", "{you} 2F", SCR_WALL_CLOCK,
     "Set the clock on the wall", None),
    (lambda m: m.var(VAR_LITTLEROOT_INTRO_STATE) >= 7 or begun(m),
     "Go back downstairs: your mom wants you to see something on TV.", "{you} 1F", None, "", None),
    (lambda m: m.var(VAR_LITTLEROOT_RIVAL_STATE) >= 3 or m.var(VAR_LITTLEROOT_TOWN_STATE) >= 1 or begun(m),
     "Go next door to Professor Birch's house and meet his child, your new neighbor, upstairs in their room.",
     "{rival} 2F", SCR_RIVALS_POKE_BALL, "Look at the Poké Ball in the room", None),
    (lambda m: m.var(VAR_ROUTE101_STATE) >= 2 or begun(m),
     "Go north out of Littleroot Town onto Route 101: someone's calling for help.", "Route 101", None, "", None),
    (begun, "Professor Birch is being chased by a wild Pokémon! Open his bag on the ground, pick a Pokémon and save "
     "him.", "Route 101", SCR_BIRCHS_BAG, "Open Professor Birch's bag", None),
    (lambda m: m.var(VAR_BIRCH_LAB_STATE) >= 3 or m.flag(FLAG_DEFEATED_RIVAL_ROUTE103),
     "Go to Professor Birch's Lab in Littleroot Town and talk to him.", LAB, SCR_BIRCH, "Talk to Professor Birch",
     None),
    (flagged(FLAG_DEFEATED_RIVAL_ROUTE103), "Find your rival on Route 103, north of Oldale Town, and battle them.",
     "Route 103", SCR_ROUTE103_RIVAL, "Battle your rival", None),
    (flagged(FLAG_SYS_POKEDEX_GET), "Go back to Professor Birch's Lab in Littleroot Town for your Pokédex.", LAB,
     SCR_BIRCH, "Talk to Professor Birch", None),
    (lambda m: m.var(VAR_PETALBURG_GYM_STATE) >= 2 or m.flag(FLAG_BADGE[0]),
     "Go west from Oldale Town along Route 102 to Petalburg City, and talk to your dad, Norman, at the Petalburg "
     "City Gym.", "Petalburg City, Gym", SCR_NORMAN, "Talk to your dad", None),
    (flagged(FLAG_BADGE[0]), "Earn the Stone Badge from Roxanne (Rock type) at the Rustboro City Gym. The way: west "
     "from Petalburg City onto Route 104, north through Petalburg Woods, then north to Rustboro City.",
     "Rustboro City, Gym", SCR_ROXANNE, "Battle Roxanne, the Gym Leader", 13),
    (lambda m: m.var(VAR_RUSTBORO_CITY_STATE) != 1 or m.flag(FLAG_RECOVERED_DEVON_GOODS), "Walk west from the Gym in "
     "Rustboro City, toward the Pokémon Center: something's happening.", "Rustboro City", ("tile", 23, 22),
     "Walk west from the Gym", None),
    (flagged(FLAG_RECOVERED_DEVON_GOODS), "Team Aqua stole the Devon Goods in Rustboro City: chase them east along "
     "Route 116 into Rusturf Tunnel and get the goods back.", "Rusturf Tunnel", SCR_RUSTURF_GRUNT,
     "Battle the Team Aqua grunt", None),
    (flagged(FLAG_RECEIVED_POKENAV), "Take the Devon Goods back to the Devon Corporation in Rustboro City and meet "
     "its president on the top floor.", "Rustboro City, Devon Corp 3F", SCR_MR_STONE, "Talk to the president", None),
    (lambda m: m.flag(FLAG_VISITED_DEWFORD_TOWN) or m.flag(FLAG_BADGE[1]), "Ask Mr. Briney in his cottage on Route "
     "104 (south of Petalburg Woods, by the sea) to sail you to Dewford Town.", "Route 104, Mr. Briney's House",
     SCR_BRINEY_HOUSE, "Talk to Mr. Briney", None),
    (flagged(FLAG_BADGE[1]), "Earn the Knuckle Badge from Brawly (Fighting type) at the Dewford Town Gym.",
     "Dewford Town, Gym", SCR_BRAWLY, "Battle Brawly, the Gym Leader", 17),
    (flagged(FLAG_DELIVERED_STEVEN_LETTER), "Deliver the letter to Steven deep in Granite Cave, north of Dewford "
     "Town.", "Granite Cave, Stevens Room", SCR_STEVEN, "Give Steven the letter", None),
    (lambda m: m.flag(FLAG_VISITED_SLATEPORT_CITY) or m.flag(FLAG_DELIVERED_DEVON_GOODS), "Ask Mr. Briney, by the "
     "dock in Dewford Town, to sail you to Slateport City.", "Dewford Town", SCR_DEWFORD_BRINEY, "Talk to Mr. Briney",
     None),
    (flagged(FLAG_DELIVERED_DEVON_GOODS), "Give the Devon Goods to Captain Stern at the Oceanic Museum in Slateport "
     "City.", "Slateport City, Oceanic Museum 2F", SCR_STERN, "Talk to Captain Stern", None),
    (flagged(FLAG_BADGE[2]), "Go north from Slateport City along Route 110 to Mauville City and earn the Dynamo Badge "
     "from Wattson (Electric type).", "Mauville City, Gym", SCR_WATTSON, "Battle Wattson, the Gym Leader", 22),
    (flagged(FLAG_DEFEATED_EVIL_TEAM_MT_CHIMNEY), "Go north on Route 111, through the Fiery Path to Route 113, "
     "Fallarbor Town and Meteor Falls; then take the cable car on Route 112 up Mt. Chimney and stop Team Magma.",
     "Mt. Chimney", SCR_MAXIE, "Battle Maxie, Team Magma's leader", 25),
    (flagged(FLAG_BADGE[3]), "Go down Jagged Pass from Mt. Chimney to Lavaridge Town and earn the Heat Badge from "
     "Flannery (Fire type).", "Lavaridge Town, Gym 1F", SCR_FLANNERY, "Battle Flannery, the Gym Leader", 27),
    (flagged(FLAG_BADGE[4]), "Go back to Petalburg City and earn the Balance Badge from your dad, Norman (Normal "
     "type).", "Petalburg City, Gym", SCR_NORMAN, "Battle your dad, Norman", 29),
    (flagged(FLAG_RECEIVED_HM_SURF), "Visit Wally's house in Petalburg City for HM03 Surf.",
     "Petalburg City, Wally's House", SCR_WALLYS_DAD, "Talk to Wally's dad", None),
    (flagged(FLAG_BADGE[5]), "Surf east of Mauville to Route 118, then Route 119 and the Weather Institute, to "
     "Fortree City; Steven on Route 120 gives you the Devon Scope. Earn the Feather Badge from Winona (Flying type).",
     "Fortree City, Gym", SCR_WINONA, "Battle Winona, the Gym Leader", 31),
    (flagged(FLAG_BADGE[6]), "On to Lilycove City, Mt. Pyre and Team Aqua's hideout, then surf east to Mossdeep City "
     "and earn the Mind Badge from Tate and Liza (Psychic type).", "Mossdeep City, Gym", SCR_TATE_LIZA,
     "Battle Tate and Liza, the Gym Leaders", 40),
    (flagged(FLAG_BADGE[7]), "After the Space Center, dive into the Seafloor Cavern, then save Sootopolis City (the "
     "Cave of Origin, Sky Pillar) and earn the Rain Badge from Juan (Water type).", "Sootopolis City, Gym 1F",
     SCR_JUAN, "Battle Juan, the Gym Leader", 44),
    (flagged(FLAG_SYS_GAME_CLEAR), "Go through Victory Road to Ever Grande City and beat the Pokémon League.",
     "Ever Grande City, Pokémon League 1F", None, "", 50),
)
GOAL_DONE = "You've beaten the Pokémon League. Explore, catch and train as you like."


def story_step(m):
    """The story's next step, from the game's flags and vars: {words, place, script, does, level}."""
    boy = m.male()
    you, rival = HOUSES if boy else HOUSES[::-1]
    for done, words, place, script, does, level in STORY:
        if not done(m):
            return {"words": words, "place": place.format(you=you, rival=rival), "does": does, "level": level,
                    "script": script[0 if boy else 1] if isinstance(script, tuple) and len(script) == 2 else script}
    return {"words": GOAL_DONE, "place": None, "script": None, "does": "", "level": None}


def supported(rom):
    """True for the cartridge this plays: Pokémon Emerald, English."""
    return len(rom) > 0x100 and rom[0xAC:0xB0] == GAME_CODE and rom[0xBC] == GAME_VERSION


def text(data, most=1000):
    """The game's letters as text: line breaks as spaces, its codes (colours, pauses) left out."""
    out, i = [], 0
    while i < min(len(data), most):
        b = data[i]
        if b == 0xFF:
            break
        if b == 0xFC:                                # a code, and what goes with it
            code = data[i + 1] if i + 1 < len(data) else 0
            i += 1 + (CTRL_LENGTHS[code] if code < len(CTRL_LENGTHS) else 1)
            continue
        if b in (0xF7, 0xF8, 0xF9, 0xFD):            # a stand-in (the player's name...), an icon: and its number
            i += 2
            continue
        if b in (0xFA, 0xFB, 0xFE):
            out.append(" ")
        else:
            out.append(CHARS.get(b, ""))
        i += 1
    return " ".join("".join(out).split())


class BadAddress(Exception):
    pass


class Mem:
    """The game's memory at one moment: its working RAM (IWRAM, EWRAM: pitato/gameai.py's snapshot) and the
    cartridge (read-only, the same throughout)."""

    def __init__(self, iwram, ewram, rom):
        self.iwram, self.ewram, self.rom = iwram, ewram, rom

    def bytes(self, addr, n):
        if EWRAM <= addr and addr + n <= EWRAM + len(self.ewram):
            o = addr - EWRAM
            return self.ewram[o:o + n]
        if IWRAM <= addr and addr + n <= IWRAM + len(self.iwram):
            o = addr - IWRAM
            return self.iwram[o:o + n]
        if ROM_BASE <= addr and addr + n <= ROM_BASE + len(self.rom):
            o = addr - ROM_BASE
            return self.rom[o:o + n]
        raise BadAddress(f"{addr:#x}")

    def u8(self, a):
        return self.bytes(a, 1)[0]

    def u16(self, a):
        return struct.unpack("<H", self.bytes(a, 2))[0]

    def s16(self, a):
        return struct.unpack("<h", self.bytes(a, 2))[0]

    def u32(self, a):
        return struct.unpack("<I", self.bytes(a, 4))[0]

    def s32(self, a):
        return struct.unpack("<i", self.bytes(a, 4))[0]

    def text(self, a, n):
        return text(self.bytes(a, n))

    def flag(self, flag):
        sb1 = self.u32(G_SAVEBLOCK1_PTR)
        return bool(self.u8(sb1 + SB1_FLAGS + flag // 8) & (1 << (flag % 8)))

    def var(self, var):
        """One of the story's vars (VAR_...)."""
        return self.u16(self.u32(G_SAVEBLOCK1_PTR) + SB1_VARS + 2 * (var - VARS_START))

    def male(self):
        """You're playing a boy (Brendan; else May)."""
        return self.u8(self.u32(G_SAVEBLOCK2_PTR) + SB2_GENDER) == 0


def code(addr):
    """A function's address as the game stores it (the low bit says thumb code): without that bit."""
    return addr & ~1


def waiting_for_a(m):
    """A script's message, read out and still up, waiting for A (the message box says it's done by then)."""
    return (m.u8(S_GLOBAL_SCRIPT_CONTEXT + 1) == SCRIPT_NATIVE
            and code(m.u32(S_GLOBAL_SCRIPT_CONTEXT + 4)) == WAIT_FOR_A_OR_B)


# ---- the cartridge's tables (read once) -----------------------------------------------------------------------------
class Rom:
    def __init__(self, rom):
        self.rom = rom
        self.m = Mem(b"", b"", rom)
        self.names, self.moves, self.attrs = {}, {}, {}
        self.effect = {}
        i = TYPE_EFFECTIVENESS - ROM_BASE
        while i + 3 <= len(rom) and rom[i] != 0xFF:
            if rom[i] != 0xFE:                     # (0xFE: Foresight's marker, before ghost's immunities)
                self.effect[(rom[i], rom[i + 1])] = rom[i + 2] / 10
            i += 3
        self.maps = {}                             # (group, num): its header's address
        for g, names in enumerate(MAP_NAMES):
            for n in range(len(names)):
                try:
                    self.maps[(g, n)] = self.m.u32(self.m.u32(MAP_GROUPS + 4 * g) + 4 * n)
                except BadAddress:
                    self.maps[(g, n)] = 0
        self.by_name = {name: (g, n) for g, names in enumerate(MAP_NAMES) for n, name in enumerate(names)}
        self.graph = None
        self.grass = {}                            # (group, num): it has tall grass

    def species(self, s):
        if s not in self.names:
            self.names[s] = self.m.text(SPECIES_NAMES + SPECIES_NAME_LEN * s, SPECIES_NAME_LEN) \
                if 0 < s < SPECIES_COUNT else "?"
        return self.names[s]

    def species_types(self, s):
        if not 0 < s < SPECIES_COUNT:
            return ()
        a = SPECIES_INFO + SPECIES_INFO_SIZE * s + 6
        t1, t2 = self.m.u8(a), self.m.u8(a + 1)
        return (t1,) if t1 == t2 else (t1, t2)

    def move(self, mv):
        """{name, power, type, accuracy, pp, effect} of a move."""
        if mv not in self.moves:
            if not 0 < mv < MOVES_COUNT:
                return None
            a = BATTLE_MOVES + BATTLE_MOVE_SIZE * mv
            effect, power, kind, acc, pp = self.m.bytes(a, 5)
            self.moves[mv] = {"name": self.m.text(MOVE_NAMES + MOVE_NAME_LEN * mv, MOVE_NAME_LEN), "power": power,
                              "type": kind, "accuracy": acc, "pp": pp, "effect": effect}
        return self.moves[mv]

    def effectiveness(self, kind, defender_types):
        k = 1.0
        for t in defender_types:
            k *= self.effect.get((kind, t), 1.0)
        return k

    def map_name(self, g, n):
        try:
            return MAP_NAMES[g][n]
        except IndexError:
            return "somewhere"

    def metatile_attrs(self, layout):
        """A map layout's tiles' behaviours (by metatile), from its two tilesets."""
        if layout not in self.attrs:
            out = []
            try:
                for which, count in ((0x10, 512), (0x14, 512)):
                    ts = self.m.u32(layout + which)
                    table = self.m.u32(ts + 0x10)
                    for i in range(count):
                        try:
                            out.append(self.m.u16(table + 2 * i) & 0xFF)
                        except BadAddress:
                            out.append(0)
            except BadAddress:
                out = [0] * 1024
            self.attrs[layout] = out
        return self.attrs[layout]

    def warps_of(self, header):
        """A map's doors and exits: [(x, y, (group, num))] in its own coordinates."""
        return [w[:3] for w in self.links_of(header)]

    def links_of(self, header):
        """A map's doors and exits, and which of the other map's they come out at: [(x, y, (group, num), its
        number there)]."""
        out = []
        try:
            events = self.m.u32(header + 4)        # (struct MapEvents: the counts, then the people, the warps...)
            count, table = self.m.u8(events + 1), self.m.u32(events + 8)
            for i in range(count):
                a = table + 8 * i
                x, y = self.m.s16(a), self.m.s16(a + 2)
                warp, num, group = self.m.u8(a + 5), self.m.u8(a + 6), self.m.u8(a + 7)
                out.append((x, y, (group, num), warp))
        except BadAddress:
            pass
        return out

    def way_around(self, here, door, to):
        """Going through a door of here's (its number) into another map comes out somewhere else on here, by
        another of its doors (as a wood between two parts of a route): a way round to the part of here that
        can't be walked to."""
        try:
            mine = self.warps_of(self.maps.get(here, 0))
            x0, y0 = mine[door][:2]
            ends = [mine[w][:2] for _, _, dest, w in self.links_of(self.maps.get(to, 0))
                    if dest == here and w < len(mine)]
        except (BadAddress, IndexError):
            return False
        return any(abs(x - x0) + abs(y - y0) > 3 for x, y in ends)

    def signs_of(self, header):
        """A map's things to look at (signs, a clock, a TV...): [(x, y, which way you face to look (0: any),
        script)] in its own coordinates. (Hidden items and secret bases aren't.)"""
        out = []
        try:
            events = self.m.u32(header + 4)        # (struct MapEvents: the bg events' count at +3, them at +0x10)
            count, table = self.m.u8(events + 3), self.m.u32(events + 0x10)
            for i in range(min(count, 64)):
                a = table + 12 * i
                kind = self.m.u8(a + 5)
                if kind <= 4:
                    out.append((self.m.u16(a), self.m.u16(a + 2), BG_FACING.get(kind, 0), self.m.u32(a + 8)))
        except BadAddress:
            pass
        return out

    def grassy(self, key):
        """A map has tall grass (for wild Pokémon), from its layout's tiles."""
        if key not in self.grass:
            found = False
            try:
                layout = self.m.u32(self.maps.get(key, 0))
                w, h, blocks = self.m.s32(layout), self.m.s32(layout + 4), self.m.u32(layout + 0xC)
                if 0 < w * h <= 0x10000:
                    attrs = self.metatile_attrs(layout)
                    tiles = struct.unpack(f"<{w * h}H", self.m.bytes(blocks, 2 * w * h))
                    found = any(attrs[t & 0x3FF] in GRASS for t in tiles if (t & 0x3FF) < len(attrs))
            except (BadAddress, struct.error):
                pass
            self.grass[key] = found
        return self.grass[key]

    def connections_of(self, header):
        """A map's roads on to the next: [(direction, offset, (group, num))]."""
        out = []
        try:
            conns = self.m.u32(header + 0xC)
            if conns:
                count, table = self.m.s32(conns), self.m.u32(conns + 4)
                for i in range(max(0, min(count, 8))):
                    a = table + 12 * i
                    d = self.m.u8(a)
                    if d in CONNECTION_DIRS:
                        out.append((CONNECTION_DIRS[d], self.m.s32(a + 4), (self.m.u8(a + 8), self.m.u8(a + 9))))
        except BadAddress:
            pass
        return out

    def map_graph(self):
        """Which maps lead to which, by doors and roads (both ways): for finding the way to a goal."""
        if self.graph is None:
            g = {k: set() for k in self.maps}
            for k, header in self.maps.items():
                for _, _, to in self.warps_of(header):
                    if to in g and to != k:
                        g[k].add(to)
                        g[to].add(k)
                for _, _, to in self.connections_of(header):
                    if to in g and to != k:
                        g[k].add(to)
                        g[to].add(k)
            self.graph = g
        return self.graph

    def distances_to(self, goal):
        """How many maps away from the goal map each map is."""
        graph = self.map_graph()
        dist, todo = {goal: 0}, deque([goal])
        while todo:
            k = todo.popleft()
            for n in graph.get(k, ()):
                if n not in dist:
                    dist[n] = dist[k] + 1
                    todo.append(n)
        return dist

    def multichoice(self, i):
        """A script's menu's choices (its words)."""
        if not 0 <= i < MULTICHOICES:
            return []
        a = MULTICHOICE_LISTS + 8 * i
        table, count = self.m.u32(a), self.m.u8(a + 4)
        out = []
        for k in range(min(count, 12)):
            try:
                out.append(self.m.text(self.m.u32(table + 8 * k), 40) or f"choice {k + 1}")
            except BadAddress:
                out.append(f"choice {k + 1}")
        return out


# ---- your Pokémon -------------------------------------------------------------------------------------------------
def party(m, rom):
    """Your Pokémon: [{slot, name, species, level, hp, max_hp, status, moves, egg}]."""
    out = []
    count = min(m.u8(G_PLAYER_PARTY_COUNT), 6)
    for slot in range(count):
        raw = m.bytes(G_PLAYER_PARTY + 100 * slot, 100)
        personality, otid = struct.unpack_from("<II", raw)
        egg = bool(raw[19] & 4)
        key = personality ^ otid
        data = struct.pack("<12I", *(v ^ key for v in struct.unpack_from("<12I", raw, 32)))
        gpos, apos = SUBSTRUCT_POS[personality % 24]
        species = struct.unpack_from("<H", data, 12 * gpos)[0]
        moves = struct.unpack_from("<4H", data, 12 * apos)
        pps = data[12 * apos + 8:12 * apos + 12]
        status, level = struct.unpack_from("<IB", raw, 80)
        hp, max_hp = struct.unpack_from("<HH", raw, 86)
        out.append({"slot": slot, "pid": personality, "name": text(raw[8:18]) or rom.species(species),
                    "species": species, "level": level, "hp": hp, "max_hp": max_hp, "status": status_words(status), "egg": egg,
                    "moves": [(mv, pps[i]) for i, mv in enumerate(moves) if mv]})
    return out


def status_words(status):
    for mask, word in STATUS_WORDS:
        if status & mask:
            return word
    return ""


def party_line(p):
    return {"name": p["name"], "level": p["level"], "hp": f"{p['hp']}/{p['max_hp']}"} | (
        {"status": p["status"]} if p["status"] else {}) | ({"egg": True} if p["egg"] else {})


def hurt(team):
    """How hurt your team is: its HP, all told, as a share of what it could be (0 to 1)."""
    live = [p for p in team if not p["egg"]]
    most = sum(p["max_hp"] for p in live)
    return 1 - sum(p["hp"] for p in live) / most if most else 0.0


# ---- a battle --------------------------------------------------------------------------------------------------------
def battler(m, rom, b):
    a = G_BATTLE_MONS + BATTLE_MON_SIZE * b
    species = m.u16(a)
    t1, t2 = m.u8(a + 0x21), m.u8(a + 0x22)
    return {"b": b, "species": species, "name": m.text(a + 0x30, 11) or rom.species(species),
            "kind": rom.species(species), "atk": m.u16(a + 2), "def": m.u16(a + 4), "spe": m.u16(a + 6),
            "spa": m.u16(a + 8), "spd": m.u16(a + 10), "moves": [m.u16(a + 0xC + 2 * i) for i in range(4)],
            "pp": list(m.bytes(a + 0x24, 4)), "types": (t1,) if t1 == t2 else (t1, t2), "hp": m.u16(a + 0x28),
            "level": m.u8(a + 0x2A), "max_hp": m.u16(a + 0x2C), "status": status_words(m.u32(a + 0x4C))}


def guess_damage(rom, user, target, mv):
    """A move's damage, roughly (the game's formula, its average roll), and how effective it is."""
    info = rom.move(mv)
    if not info or info["power"] <= 1:
        return 0, rom.effectiveness(info["type"], target["types"]) if info else 1.0
    special = info["type"] in SPECIAL_TYPES
    a, d = (user["spa"], target["spd"]) if special else (user["atk"], target["def"])
    base = ((2 * user["level"] / 5 + 2) * info["power"] * max(a, 1) / max(d, 1)) / 50 + 2
    stab = 1.5 if info["type"] in user["types"] else 1.0
    k = rom.effectiveness(info["type"], target["types"])
    return base * stab * k * 0.92 * (info["accuracy"] or 100) / 100, k


def effect_words(k):
    if k == 0:
        return "no effect"
    if k > 1:
        return "super effective"
    if k < 1:
        return "not very effective"
    return ""


# ---- the map you're on -----------------------------------------------------------------------------------------
class Field:
    """The map at one moment: its tiles (with the roads around it), where you are, the people, the doors."""

    def __init__(self, m, rom):
        self.m, self.rom = m, rom
        sb1 = m.u32(G_SAVEBLOCK1_PTR)
        self.where = (m.u8(sb1 + SB1_LOCATION) & 0xFF, m.u8(sb1 + SB1_LOCATION + 1) & 0xFF)
        self.came_from = (m.u8(sb1 + SB1_DYNAMIC_WARP), m.u8(sb1 + SB1_DYNAMIC_WARP + 1))
        self.name = rom.map_name(*self.where)
        self.header = rom.maps.get(self.where, 0)
        layout = m.u32(G_MAP_HEADER)
        self.layout_id = m.u16(G_MAP_HEADER + 0x12)
        self.lw, self.lh = (m.s32(layout), m.s32(layout + 4)) if layout >= ROM_BASE else (0, 0)
        self.w, self.h = m.s32(G_BACKUP_MAP_LAYOUT), m.s32(G_BACKUP_MAP_LAYOUT + 4)
        mp = m.u32(G_BACKUP_MAP_LAYOUT + 8)
        self.blocks = struct.unpack(f"<{self.w * self.h}H", m.bytes(mp, 2 * self.w * self.h)) \
            if 0 < self.w * self.h <= 0x20000 else ()
        self.attrs = rom.metatile_attrs(layout) if layout >= ROM_BASE else [0] * 1024
        avatar = G_PLAYER_AVATAR
        self.avatar_flags = m.u8(avatar)
        self.surfing = bool(self.avatar_flags & AVATAR_SURFING)
        me = m.u8(avatar + 5)
        self.people, self.blockers = [], []
        self.me = None
        for i in range(OBJECT_EVENTS):
            a = G_OBJECT_EVENTS + OBJECT_EVENT_SIZE * i
            bits = m.u32(a)
            if not bits & 1:
                continue
            o = {"i": i, "gfx": m.u8(a + 5), "trainer_type": m.u8(a + 7), "local_id": m.u8(a + 8),
                 "x": m.s16(a + 0x10), "y": m.s16(a + 0x12), "px": m.s16(a + 0x14), "py": m.s16(a + 0x16),
                 "elev": m.u8(a + 0xB) & 0xF, "facing": m.u16(a + 0x18) & 0xF, "invisible": bool(bits & (1 << 13))}
            if i == me or bits & (1 << 16):
                self.me = o
            else:
                self.blockers.append(o)            # (unseen ones block the way too)
                if not o["invisible"]:
                    self.people.append(o)
        self.x, self.y = (self.me["x"], self.me["y"]) if self.me else (0, 0)
        self.elev = self.me["elev"] if self.me else 0
        self.facing = self.me["facing"] if self.me else SOUTH
        self.templates = self.read_templates()
        self.warps = [(x + MAP_OFFSET, y + MAP_OFFSET, to) for x, y, to in rom.warps_of(self.header)] \
            if self.header else []
        self.roads = rom.connections_of(self.header) if self.header else []
        self.signs = [(x + MAP_OFFSET, y + MAP_OFFSET, d, script) for x, y, d, script in rom.signs_of(self.header)] \
            if self.header else []

    def read_templates(self):
        """The map's people as placed (by their number): their script, for whether a trainer's been beaten."""
        out = {}
        try:
            events = self.m.u32(G_MAP_HEADER + 4)
            count, table = self.m.u8(events), self.m.u32(events + 4)
            for k in range(min(count, 64)):
                a = table + 0x18 * k
                out[self.m.u8(a)] = self.m.u32(a + 0x10)
        except BadAddress:
            pass
        return out

    def script_of(self, person):
        """The script someone runs when you talk to them (their number's, as placed), or None."""
        return self.templates.get(person["local_id"])

    def trainer_flag(self, person):
        """An unbeaten trainer's flag, or None: not a trainer, or beaten."""
        script = self.templates.get(person["local_id"])
        try:
            if script and self.m.u8(script) == SCR_OP_TRAINERBATTLE:
                flag = TRAINER_FLAGS_START + self.m.u16(script + 2)
                return None if self.m.flag(flag) else flag
        except BadAddress:
            pass
        return None

    def block(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.blocks[x + self.w * y]
        return BLOCK_UNDEFINED

    def behaviour(self, x, y):
        b = self.block(x, y)
        return self.attrs[b & 0x3FF] if (b & 0x3FF) < len(self.attrs) else 0

    def inside(self, x, y):
        """On this map itself (not the next one along a road, nor off the edge)."""
        return MAP_OFFSET <= x < MAP_OFFSET + self.lw and MAP_OFFSET <= y < MAP_OFFSET + self.lh

    def occupied(self):
        """Where people are (and the tiles they're stepping off): {(x, y): their heights}."""
        tiles = {}
        for p in self.blockers:
            for t in ((p["x"], p["y"]), (p["px"], p["py"])):
                tiles.setdefault(t, set()).add(p["elev"])
        return tiles

    def step(self, x, y, elev, d, occupied, avoid, surfing):
        """Where a step from (x, y) going d gets you: (x, y, elevation, still surfing), or None (you can't)."""
        dx, dy = STEP[d]
        nx, ny = x + dx, y + dy
        b = self.block(nx, ny)
        if b == BLOCK_UNDEFINED or in_the_way(occupied, nx, ny, elev):
            return None
        here, there = self.behaviour(x, y), self.behaviour(nx, ny)
        if here in BLOCKED_GOING[d] or there in BLOCKED_COMING[d]:
            return None
        if MB_JUMP.get(there) == d and not surfing:   # a ledge: over it, two along
            lx, ly = nx + dx, ny + dy
            lb = self.block(lx, ly)
            if lb == BLOCK_UNDEFINED or (lb >> 10) & 3 or (lx, ly) in occupied or (lx, ly) in avoid:
                return None
            return lx, ly, lb >> 12 or elev, False
        if (b >> 10) & 3 or (nx, ny) in avoid:
            return None
        e = b >> 12
        if surfing:                                # on the water: on along it, or off onto land (walking from there)
            if e == LAND:
                return nx, ny, LAND, False
            return (nx, ny, WATER, True) if e in (0, WATER, 15) else None
        if elev not in (0, 15) and e not in (0, 15) and e != elev:
            return None                            # (water's lower: not without Surf)
        return nx, ny, (e if e != 15 else elev), False

    def reach(self, avoid=frozenset(), most=40000):
        """Every tile you can walk to from here: (every way there, {(x, y): (steps, how you got there)})."""
        occupied = self.occupied()
        start = (self.x, self.y, self.elev, self.surfing)
        seen = {start: (0, None)}
        todo = deque([start])
        while todo and len(seen) < most:
            s = todo.popleft()
            for d in (NORTH, SOUTH, WEST, EAST):
                n = self.step(s[0], s[1], s[2], d, occupied, avoid, s[3])
                if n is not None and n not in seen:
                    seen[n] = (seen[s][0] + 1, (s, d))
                    todo.append(n)
        tiles = {}
        for s, v in seen.items():
            if (s[0], s[1]) not in tiles or v[0] < tiles[(s[0], s[1])][0]:
                tiles[(s[0], s[1])] = (v[0], s)
        return seen, tiles

    def path(self, seen, tiles, x, y):
        """The steps (directions) from here to (x, y), from reach()."""
        if (x, y) not in tiles:
            return None
        s = tiles[(x, y)][1]
        out = []
        while seen[s][1] is not None:
            prev, d = seen[s][1]
            out.append(d)
            s = prev
        return out[::-1]


def in_the_way(occupied, x, y, elev):
    """Someone's on that tile at a height that meets yours (the game: either at 0, or both the same)."""
    return any(e == 0 or elev == 0 or e == elev for e in occupied.get((x, y), ()))


def way(dx, dy):
    """A direction in words, roughly: "north-east"."""
    ns = "north" if dy < 0 else "south" if dy > 0 else ""
    ew = "east" if dx > 0 else "west" if dx < 0 else ""
    if abs(dx) > 2 * abs(dy):
        ns = ""
    if abs(dy) > 2 * abs(dx):
        ew = ""
    return "-".join(w for w in (ns, ew) if w) or "here"


# ---- the player -------------------------------------------------------------------------------------------------------
class Stop(Exception):
    """The AI player's been turned off (or the game's ended)."""


class Emerald:
    """Plays Pokémon Emerald through io (pitato/gameai.py's GameIO: the game's memory, its buttons, the model)."""

    def __init__(self, rom_bytes, io):
        self.rom = Rom(rom_bytes)
        self.io = io
        self.recent = deque(maxlen=RECENT)
        self.seen = {}                              # tiles you've had in view, map by map
        self.since, self.mode_was = time.monotonic(), None
        self.plan = None                            # a decision carried over: the move to forget, who to send out
        self.tried = {}                             # what didn't work, and where: not offered again for a while
        self.last_where = None
        self.goal_cache = {}
        self.walks = deque(maxlen=SAME_PICK[1])     # (where, pick): the last few, out walking
        self.move_tried = None                      # (battler, move slot, when): a move just picked
        self.said = deque(maxlen=SAID)              # what people said lately (the game's messages)
        self.came_in = {}                           # each map: where you came in, last time (x, y)
        self.taken = {}                             # (a map, a way out of it): how often it's been taken
        self.starter = None                         # the first Pokémon picked (its place in the bag: 0 to 2)

    # -- the loop ---------------------------------------------------------------------------------------------------
    def play(self):
        errors = 0
        while True:
            try:
                m = self.io.snapshot()
                mode = self.mode(m)
                if mode[0] != self.mode_was:
                    self.mode_was, self.since = mode[0], time.monotonic()
                getattr(self, "on_" + mode[0])(m, *mode[1:])
                errors = 0
            except Stop:
                raise
            except (BadAddress, struct.error, IndexError, KeyError, ValueError, ZeroDivisionError) as ex:
                errors += 1                        # (memory caught mid-change, a map loading: a moment, and again)
                self.io.log(event="A look that didn't make sense", error=f"{type(ex).__name__}: {ex}")
                if errors > ERRORS_MOST:
                    raise
                self.io.wait(0.5)

    def stuck(self):
        return time.monotonic() - self.since > STUCK_AFTER

    def mode(self, m):
        """What's on: ("battle_action", b), ("text",), ("walk",)... (a method on_<it> for each)."""
        cb2 = code(m.u32(G_MAIN + 4))
        tasks = self.tasks(m)
        if cb2 == CB2_BATTLE:
            positions = m.bytes(G_BATTLER_POSITIONS, 4)
            for b in range(min(m.u8(G_BATTLERS_COUNT), 4)):
                if positions[b] & 1:
                    continue
                f = code(m.u32(G_BATTLER_CONTROLLER_FUNCS + 4 * b))
                if f == CHOOSE_ACTION:
                    return ("battle_action", b)
                if f == CHOOSE_MOVE:
                    return ("battle_move", b)
                if f == CHOOSE_TARGET:
                    return ("tap", "a", "Picking the target")
                if f == SWITCH_YES_NO:
                    return ("switch_question",)
            try:
                op = m.u8(m.u32(G_BATTLESCRIPT_CURR_INSTR))
            except BadAddress:
                op = None
            # its yes or no is up once that command's step is 1 (the learn-move boxes keep theirs elsewhere)
            step = G_BATTLE_SCRIPTING_LEARN_MOVE if op in (OP_LEARN_MOVE, OP_STOP_LEARNING) else G_BATTLE_COMMUNICATION
            if op in (OP_YES_NO, OP_LEARN_MOVE, OP_STOP_LEARNING, OP_NICKNAME) and m.u8(step) == 1:
                return ("battle_question", op)
            return ("battle_wait",)
        if cb2 == CB2_PARTY_MENU:
            if TASK_PARTY_SELECTION in tasks:
                return ("tap", "a", "Sending a Pokémon out")
            return ("party_menu",)
        if cb2 == CB2_SUMMARY:
            if TASK_REPLACE_MOVE in tasks:
                return ("forget_move",)
            return ("wait_then", "b")
        if cb2 in CB2_EVOLUTION:
            return ("wait_then", "a")
        if cb2 == CB2_NAMING_SCREEN:
            return ("naming",)
        if cb2 == CB2_BAG:
            return ("wait_then", "b")
        if cb2 == CB2_TITLE:
            return ("tap", "start", "Starting the game")
        if cb2 == CB2_MAIN_MENU:                   # (CONTINUE, or NEW GAME with no save; then Birch's talk)
            return ("tap", "a", "Starting the game")
        if cb2 == CB2_WALL_CLOCK:                  # (the time as it is: A, then YES)
            if TASK_SET_CLOCK in tasks:
                return ("tap", "a", "Setting the clock")
            if TASK_CONFIRM_CLOCK in tasks:
                return ("yes", "Setting the clock")
            if TASK_VIEW_CLOCK in tasks:
                return ("tap", "b", "Done with the clock")
            return ("wait",)
        if cb2 == CB2_STARTER:
            if TASK_CHOOSE_STARTER in tasks:
                return ("starter", tasks[TASK_CHOOSE_STARTER])
            if TASK_CONFIRM_STARTER in tasks:
                return ("yes", "Choosing your first Pokémon")
            return ("wait",)
        if cb2 == CB2_OVERWORLD:
            if TASK_YES_NO in tasks:
                return ("question",)
            if TASK_MULTICHOICE in tasks:
                return ("choice", tasks[TASK_MULTICHOICE])
            if TASK_START_MENU in tasks:
                return ("tap", "b", "Closing the menu")
            if m.u8(S_FIELD_MESSAGE_BOX_MODE) or waiting_for_a(m):
                return ("text",)
            if m.u8(G_PALETTE_FADE + 7) & 0x80 or m.u8(S_LOCK_FIELD_CONTROLS) or m.u8(G_PLAYER_AVATAR + 3):
                return ("wait_then", "a")
            return ("walk",)
        return ("wait_then", "b")                  # (a screen it doesn't know, a shop's say: out of it, in a while)

    def tasks(self, m):
        """The game's running tasks: {function: the task's data}."""
        out = {}
        for i in range(TASKS):
            a = G_TASKS + TASK_SIZE * i
            if m.u8(a + 4):
                out[code(m.u32(a))] = struct.unpack("<16h", m.bytes(a + 8, 32))
        return out

    # -- small things ----------------------------------------------------------------------------------------------
    def on_wait(self, m):
        self.io.wait(WAIT_EVERY)

    def on_wait_then(self, m, button):
        """Nothing to do but wait (a fade, a script walking you somewhere); if it's long, a button."""
        if self.stuck():
            self.io.tap(button)
            self.since = time.monotonic() - STUCK_AFTER / 2
        self.io.wait(WAIT_EVERY)

    def on_tap(self, m, button, what):
        self.io.status(what)
        self.io.tap(button)
        self.io.wait(TEXT_EVERY)

    def on_text(self, m):
        words = m.text(G_STRING_VAR4, 300)
        if words and (not self.said or self.said[-1] != words):
            self.said.append(words)                # (what people say: the model's told the last few)
        self.io.status("Reading: " + words[:60])
        self.io.tap("a")
        self.io.wait(TEXT_EVERY)

    def on_yes(self, m, what):
        """A yes or no that's to be yes (the clock's time, the Pokémon picked): the cursor to YES, A."""
        self.io.status(what)
        self.move_cursor(lambda: self.io.peek_u8(S_MENU + 2), 0)
        self.io.tap("a")
        self.io.wait(0.4)

    def on_starter(self, m, data):
        """Professor Birch's bag: the model picks your first Pokémon (once); the cursor there, A."""
        if self.starter is None:
            choices = dict(STARTERS)
            pick = self.io.decide("starter", SAYS_STARTER, {"choosing": "your first Pokémon"}, choices, "mudkip")
            self.starter = [k for k, _ in STARTERS].index(pick)
            self.remember("Chose " + choices[pick].split(" (")[0] + " as your first Pokémon")
        now = data[0]
        self.io.status("Choosing " + STARTERS[self.starter][1].split(" (")[0])
        if now == self.starter:
            self.io.tap("a")
            self.io.wait(0.6)
            return
        self.io.tap("right" if now < self.starter else "left")
        self.io.wait(0.4)

    def on_battle_wait(self, m):
        """A battle going on by itself (moves, text): A now and then, which hurries its text along (after a fresh
        look: not on your menu, if it's just come up, which would pick whatever the cursor's on)."""
        if time.monotonic() - self.since > 1.0:
            if self.mode(self.io.snapshot())[0] == "battle_wait":
                self.io.tap("a")
            self.since = time.monotonic() - 0.6
        self.io.wait(WAIT_EVERY)

    def on_naming(self, m):
        """A naming screen (a nickname): the name as it is (START, then A on OK)."""
        self.io.status("Keeping the name")
        self.io.tap("start")
        self.io.wait(0.3)
        self.io.tap("a")
        self.io.wait(0.5)

    def remember(self, what):
        self.recent.append(what)
        self.io.log(event=what)

    # -- answers -----------------------------------------------------------------------------------------------------
    def move_cursor(self, read, want, keys=("up", "down"), most=12):
        """Up or down until a menu's cursor (read from memory) is on want."""
        for _ in range(most):
            now = read()
            if now == want or now is None:
                return now == want
            self.io.tap(keys[1] if now < want else keys[0])
            self.io.wait(0.1)
        return read() == want

    def on_question(self, m):
        """A yes or no, out walking: the model answers, from the question."""
        q = m.text(G_STRING_VAR4, 400)
        state = self.state(m) | {"question": q}
        fallback = "no" if "nickname" in q.lower() else "yes"
        pick = self.io.decide("question", SAYS_ANSWER, state, {"yes": "Yes", "no": "No"}, fallback)
        self.remember(f"Answered {pick} to: {q[:80]}")
        self.io.status(f"Answering {pick}")
        self.move_cursor(lambda: self.io.peek_u8(S_MENU + 2), 0 if pick == "yes" else 1)
        self.io.tap("a")
        self.io.wait(0.4)

    def on_choice(self, m, data):
        """A menu of a few choices (a script's multichoice): the model picks."""
        options = self.rom.multichoice(data[7])
        choices = {f"c{k}": o for k, o in enumerate(options) if o.upper() not in CANT_DO}
        if not choices:
            self.io.tap("b")
            self.io.wait(0.3)
            return
        q = m.text(G_STRING_VAR4, 400)
        state = self.state(m) | {"question": q}
        pick = self.io.decide("choice", SAYS_ANSWER, state, choices, next(iter(choices)))
        want = int(pick[1:])
        self.remember(f"Chose {options[want]} for: {q[:80]}")
        self.io.status("Choosing " + options[want])
        self.move_cursor(lambda: self.io.peek_s8(S_MENU + 2), want)
        self.io.tap("a")
        self.io.wait(0.4)

    def on_switch_question(self, m):
        """A trainer's next Pokémon is coming: switch? (No: the battle's choice of moves is the model's.)"""
        self.move_cursor(lambda: self.io.peek_u8(G_MULTI_USE_PLAYER_CURSOR), 1)
        self.io.tap("a")
        self.io.wait(0.4)

    def on_battle_question(self, m, op):
        cursor = lambda: self.io.peek_u8(G_BATTLE_COMMUNICATION + 1)   # noqa: E731 (0 yes, 1 no)
        q = m.text(G_DISPLAYED_STRING_BATTLE, 300)
        if op == OP_NICKNAME:
            yes = False
        elif op == OP_STOP_LEARNING:              # "Stop learning X?": yes, unless a move to forget was picked
            yes = not (self.plan and self.plan[0] == "forget")
        elif op == OP_LEARN_MOVE:
            yes = self.decide_learning(m)
        else:                                     # "Use next Pokémon?" and the like
            state = self.state(m) | {"question": q}
            yes = self.io.decide("question", SAYS_ANSWER, state, {"yes": "Yes", "no": "No"}, "yes") == "yes"
        self.io.status(("Yes: " if yes else "No: ") + q[:50])
        self.move_cursor(cursor, 0 if yes else 1)
        self.io.tap("a")
        self.io.wait(0.4)

    def decide_learning(self, m):
        """A new move to learn, with four already: the model picks one to forget (or not to learn it)."""
        new = m.u16(G_MOVE_TO_LEARN)
        team = party(m, self.rom)
        try:
            slot = m.u8(m.u32(G_BATTLE_STRUCT) + EXP_GETTER)
        except BadAddress:
            slot = -1
        mon = next((p for p in team if p["slot"] == slot), None)
        mon = mon or max(team, key=lambda p: p["level"], default=None)
        info = self.rom.move(new) or {"name": "?", "type": 0, "power": 0}
        choices = {"skip": f"Don't learn {info['name']}"}
        if mon:
            for k, (mv, _) in enumerate(mon["moves"][:4]):
                if mv == new or mv in HM_MOVES:
                    continue
                old = self.rom.move(mv) or {"name": "?", "type": 0, "power": 0}
                choices[f"forget{k}"] = (f"Forget {old['name']} ({TYPES[old['type']]}, power {old['power']}) to "
                                         f"learn {info['name']} ({TYPES[info['type']]}, power {info['power']})")
        state = {"pokemon": mon["name"] if mon else "?", "new_move": self.move_line(new)}
        fallback = "skip"
        if mon:
            weakest = min((k for k in range(len(mon["moves"])) if f"forget{k}" in choices),
                          key=lambda k: (self.rom.move(mon["moves"][k][0]) or {"power": 0})["power"], default=None)
            if weakest is not None and info["power"] > (self.rom.move(mon["moves"][weakest][0]) or {"power": 0})["power"]:
                fallback = f"forget{weakest}"
        pick = self.io.decide("learn", SAYS_LEARN, state, choices, fallback)
        self.plan = ("forget", int(pick[6:])) if pick.startswith("forget") else None
        self.remember(choices[pick])
        return self.plan is not None

    def on_forget_move(self, m):
        """The summary screen, to forget a move: the cursor to the one picked, A."""
        want = self.plan[1] if self.plan and self.plan[0] == "forget" else 4   # (4: the new one: don't learn it)
        ptr = m.u32(S_MON_SUMMARY_SCREEN)
        self.move_cursor(lambda: self.io.peek_u8(ptr + SUMMARY_MOVE_CURSOR), want)
        self.io.tap("a")
        self.plan = None
        self.io.wait(0.6)

    def move_line(self, mv, user=None, target=None, pp=None):
        info = self.rom.move(mv)
        if not info:
            return "?"
        words = [info["name"], TYPES[info["type"]], f"power {info['power']}" if info["power"] > 1 else "no damage"]
        if user and target:
            dmg, k = guess_damage(self.rom, user, target, mv)
            if info["power"] > 1 and target["hp"]:
                words.append(f"about {min(100, round(100 * dmg / target['hp']))}% of its HP")
            if effect_words(k):
                words.append(effect_words(k))
        if pp is not None:
            words.append(f"{pp} PP left")
        return ", ".join(words)

    # -- a battle ------------------------------------------------------------------------------------------------------
    def foe_of(self, m, b):
        positions = m.bytes(G_BATTLER_POSITIONS, 4)
        count = min(m.u8(G_BATTLERS_COUNT), 4)
        foes = [battler(m, self.rom, k) for k in range(count) if positions[k] & 1]
        live = [f for f in foes if f["hp"] > 0] or foes
        return live[0] if live else None

    def on_battle_action(self, m, b):
        """Your turn: a move, a switch, or running away (a wild battle). The model picks."""
        me, foe = battler(m, self.rom, b), self.foe_of(m, b)
        flags = m.u32(G_BATTLE_TYPE_FLAGS)
        trainer = bool(flags & BATTLE_TRAINER)
        team = party(m, self.rom)
        out_now = {m.u16(G_BATTLER_PARTY_INDEXES + 2 * k) for k in range(min(m.u8(G_BATTLERS_COUNT), 4))
                   if not m.bytes(G_BATTLER_POSITIONS, 4)[k] & 1}
        choices, scores = {}, {}
        for k, mv in enumerate(me["moves"]):
            if mv and me["pp"][k] > 0:
                choices[f"move{k}"] = "Use " + self.move_line(mv, me, foe, me["pp"][k])
                dmg, _ = guess_damage(self.rom, me, foe, mv) if foe else (0, 1)
                scores[f"move{k}"] = dmg
        for p in team:
            if p["slot"] not in out_now and p["hp"] > 0 and not p["egg"]:
                types = self.rom.species_types(p["species"])
                choices[f"switch{p['slot']}"] = (f"Switch to {p['name']} (level {p['level']}, "
                                                 f"{p['hp']}/{p['max_hp']} HP, {'/'.join(TYPES[t] for t in types)})")
        if not trainer and not flags & BATTLE_SAFARI:
            choices["run"] = "Run away"
        if not choices:                            # (no PP at all: FIGHT, and the game struggles)
            choices["move0"] = "Fight"
            scores["move0"] = 1
        fallback = max(scores, key=scores.get) if scores else next(iter(choices))
        if (not trainer and "run" in choices and me["hp"] < me["max_hp"] / 5
                and not any(k.startswith("switch") for k in choices)):
            fallback = "run"
        state = {"battle": "a trainer's" if trainer else "a wild Pokémon",
                 "you": {"name": me["name"], "level": me["level"], "hp": f"{me['hp']}/{me['max_hp']}",
                         "types": [TYPES[t] for t in me["types"]]} | ({"status": me["status"]} if me["status"] else {}),
                 "opponent": ({"name": foe["kind"], "level": foe["level"],
                               "hp": f"{round(100 * foe['hp'] / max(foe['max_hp'], 1))}%",
                               "types": [TYPES[t] for t in foe["types"]]} |
                              ({"status": foe["status"]} if foe["status"] else {})) if foe else {},
                 "team": [party_line(p) for p in team]}
        pick = self.io.decide("battle", SAYS_BATTLE, state, choices, fallback)
        self.io.status(choices[pick][:60])
        self.remember(f"In battle with {foe['kind'] if foe else '?'}: {choices[pick][:60]}")
        if pick.startswith("move"):
            self.move_tried = (b, int(pick[4:]), time.monotonic())
            self.choose_action(b, 0)
            self.choose_move(b, int(pick[4:]))
        elif pick.startswith("switch"):                # (by who it is: the party menu puts them in battle order)
            self.plan = ("send", next(p["pid"] for p in team if p["slot"] == int(pick[6:])))
            self.choose_action(b, 2)
        else:
            self.choose_action(b, 3)
        self.io.wait(0.5)

    def choose_action(self, b, want):
        """FIGHT (0), BAG (1), POKéMON (2), RUN (3): the cursor there (a 2x2 grid), A."""
        self.grid_cursor(lambda: self.io.peek_u8(G_ACTION_CURSOR + b), want)
        self.io.tap("a")
        self.io.wait(0.4)

    def grid_cursor(self, read, want, most=4):
        """A 2x2 menu's cursor (read from memory) onto want: up and left first, since the game won't go right
        or down onto a place with nothing in it (a Pokémon with three moves: bottom-left to top-right is up,
        then right)."""
        for _ in range(most):
            now = read()
            if now == want or now is None:
                return
            diff = now ^ want
            if diff & 2 and not want & 2:
                self.io.tap("up")
            elif diff & 1 and not want & 1:
                self.io.tap("left")
            elif diff & 1:
                self.io.tap("right")
            else:
                self.io.tap("down")
            self.io.wait(0.1)

    def on_battle_move(self, m, b):
        """The move menu's up (after FIGHT): the best move, by the model."""
        me, foe = battler(m, self.rom, b), self.foe_of(m, b)
        choices, scores = {}, {}
        refused = None                             # (a move just picked that the game said no to: disabled...)
        if self.move_tried and self.move_tried[0] == b and time.monotonic() - self.move_tried[2] < 15:
            refused = self.move_tried[1]
        for k, mv in enumerate(me["moves"]):
            if mv and me["pp"][k] > 0 and k != refused:
                choices[f"move{k}"] = "Use " + self.move_line(mv, me, foe, me["pp"][k])
                scores[f"move{k}"] = guess_damage(self.rom, me, foe, mv)[0] if foe else 0
        if not choices:
            self.io.tap("b")
            self.io.wait(0.3)
            return
        pick = self.io.decide("battle", SAYS_BATTLE, {"you": me["name"], "opponent": foe["kind"] if foe else "?"},
                              choices, max(scores, key=scores.get))
        self.move_tried = (b, int(pick[4:]), time.monotonic())
        self.choose_move(b, int(pick[4:]))

    def choose_move(self, b, want):
        """The move menu (a 2x2 grid too): the cursor on the move, A; then A on the target, if it asks."""
        read = lambda: self.io.peek_u8(G_MOVE_CURSOR + b)   # noqa: E731
        for _ in range(6):
            if self.io.peek_u32(G_BATTLER_CONTROLLER_FUNCS + 4 * b, code=True) == CHOOSE_MOVE:
                break
            self.io.wait(0.1)
        else:
            return                                 # (no move menu: struggling, or something else came up)
        self.grid_cursor(read, want)
        self.io.tap("a")
        self.io.wait(0.4)

    def on_party_menu(self, m):
        """The party menu in a battle (one's fainted, or you're switching): the cursor to the Pokémon, A. (The
        game puts the party in battle order while it's up: the slots here are the menu's.)"""
        team = party(m, self.rom)
        ok = [p for p in team if p["hp"] > 0 and not p["egg"]]
        if not ok:
            self.io.tap("b")
            self.io.wait(0.4)
            return
        planned = next((p for p in ok if self.plan and self.plan[0] == "send" and p["pid"] == self.plan[1]), None)
        if planned:
            slot = planned["slot"]
        else:
            in_battle = m.u8(G_MAIN + 0x439) & 2
            if not in_battle:                      # (opened out walking: not this one's to use)
                self.io.tap("b")
                self.io.wait(0.4)
                return
            foe = self.foe_of(m, 0)
            choices = {}
            for p in ok:
                types = self.rom.species_types(p["species"])
                choices[f"slot{p['slot']}"] = (f"Send out {p['name']} (level {p['level']}, {p['hp']}/{p['max_hp']} HP, "
                                               f"{'/'.join(TYPES[t] for t in types)})")
            state = {"opponent": ({"name": foe["kind"], "level": foe["level"],
                                   "types": [TYPES[t] for t in foe["types"]]} if foe else {})}
            best = max(ok, key=lambda p: (p["hp"] / max(p["max_hp"], 1), p["level"]))
            pick = self.io.decide("battle", SAYS_BATTLE, state, choices, f"slot{best['slot']}")
            slot = int(pick[4:])
        self.plan = None
        self.io.status(f"Sending out {next(p['name'] for p in team if p['slot'] == slot)}")
        self.move_cursor(lambda: self.io.peek_s8(G_PARTY_MENU + 9), slot, most=8)
        self.io.tap("a")
        self.io.wait(0.5)

    # -- out walking ---------------------------------------------------------------------------------------------------
    def state(self, m):
        """What the model's told, whatever it's deciding: the goal, where you are, your team, what people said."""
        try:
            f = Field(m, self.rom)
            where = f.name
        except BadAddress:
            where = "?"
        team = party(m, self.rom)
        sb1, sb2 = m.u32(G_SAVEBLOCK1_PTR), m.u32(G_SAVEBLOCK2_PTR)
        money = m.u32(sb1 + SB1_MONEY) ^ m.u32(sb2 + SB2_ENCRYPTION_KEY)
        badges = sum(m.flag(f) for f in FLAG_BADGE)
        step = self.step(m)
        out = {"goal": step["words"], "where": where, "badges": badges, "money": money,
               "team": [party_line(p) for p in team], "recently": list(self.recent)}
        if self.said:
            out["people said, lately"] = list(self.said)
        if self.weak(team, step):
            out["note"] = (f"Your team's not strong enough for that yet: train it in tall grass till your best "
                           f"Pokémon's level {step['level']}.")
        return out

    def step(self, m):
        """The story's next step (story_step())."""
        return story_step(m)

    def goal(self, m):
        """(what to do next, the map to get to) by the story's flags and vars."""
        step = self.step(m)
        return step["words"], step["place"]

    def weak(self, team, step):
        """Your team's too weak for the story's next step: its best Pokémon's below the level it should be."""
        best = max((p["level"] for p in team if not p["egg"]), default=0)
        return bool(step.get("level")) and best > 0 and best < step["level"]

    def aim(self, m, f, team, step):
        """Where it's heading now, and why: ("heal", a Pokémon Center) when your team's badly hurt; ("train", the
        nearest map with tall grass) when it's too weak for what's next; else ("story", the story's next place).
        The map's name, or None (nowhere known)."""
        if hurt(team) > HEAL_AT:
            near = self.nearest_map(f, lambda key, name: name.endswith("Pokémon Center 1F"))
            if near:
                return "heal", near
        if self.weak(team, step):                  # (outdoors: a route, the woods; here, if it's grassy itself)
            near = self.nearest_map(f, lambda key, name: "," not in name and self.rom.grassy(key), most=4)
            if near:
                return "train", near
        return "story", step["place"]

    def nearest_map(self, f, want, most=8):
        """The nearest map (by doors and roads; this one first) that's wanted (want(its (group, num), its name)),
        within most of them away; or None."""
        dist = self.rom.distances_to(f.where)
        for key in sorted(dist, key=dist.get):
            if dist[key] > most:
                break
            if want(key, self.rom.map_name(*key)):
                return self.rom.map_name(*key)
        return None

    def on_walk(self, m):
        """Free to walk: what to do next. The story's next thing, if it's here; else the way toward where it is (or
        first to heal, or to train in tall grass); and only when that's not known, the model picks from what's
        around (doors and roads, people, grass, places not yet seen). Then this walks there and does it."""
        f = Field(m, self.rom)
        if f.where != self.last_where:
            self.last_where = f.where
            self.came_in[f.where] = (f.x, f.y)
            self.remember(f"Arrived in {f.name}")
        seen = self.seen.setdefault(f.where, set())
        for dx in range(-7, 8):
            for dy in range(-5, 6):
                seen.add((f.x + dx, f.y + dy))
        step = self.step(m)
        team = party(m, self.rom)
        options = self.options(m, f, step, team)
        if not options:
            self.io.status("Looking around")
            self.wander(f)
            return
        lately = [k for w, k in self.walks if w == f.where]   # going round in circles: left out a while
        tired = {k for k in lately if lately.count(k) >= SAME_PICK[0] and k not in ("explore", "grass")}
        if set(options) - tired:
            options = {k: o for k, o in options.items() if k not in tired}
        pick, why = self.sure(f, options, step, team)
        if pick is None:
            choices = {k: o["words"] for k, o in options.items()}
            state = self.state(m) | {"here": f.name}
            pick = self.io.decide("walk", SAYS_WALK, state, choices, self.fallback(m, f, options))
        else:
            self.io.log(kind="walk", pick=pick, by=why, words=options[pick]["words"])
        self.walks.append((f.where, pick))
        o = options[pick]
        self.io.status(o["words"][:60])
        self.remember(o["words"])
        ok = self.carry_out(f, o)
        if not ok:
            self.tried[(f.where, pick)] = time.monotonic()
        elif o["kind"] in ("door", "road"):
            key = (f.where, self.exit_key(o))
            self.taken[key] = self.taken.get(key, 0) + 1

    def exit_key(self, o):
        return ("door", o["x"], o["y"]) if o["kind"] == "door" else ("road", o["dir"])

    def exit_rank(self, f, o):
        """Which way out to take first, of those toward where it's heading: not the way it came in, then one it's
        taken least from here, then the nearest. (So a way that led nowhere new is left for another next time.)"""
        came = self.came_in.get(f.where)
        back = came is not None and o["kind"] == "door" and abs(o["x"] - came[0]) + abs(o["y"] - came[1]) <= 2
        return back, self.taken.get((f.where, self.exit_key(o)), 0), o.get("steps", 0)

    def sure(self, f, options, step, team):
        """A pick that needs no asking, and why: healing (your team's badly hurt and there's a nurse or a Pokémon
        Center), the story's thing to do here, training in the grass (your team's too weak for what's next), or the
        nearest way toward where it's heading. (None, ""): there's none (the model picks)."""
        if hurt(team) > HEAL_AT:
            heal = [k for k, o in options.items() if o.get("heal")]
            if heal:
                return min(heal, key=lambda k: options[k].get("steps", 0)), "heal"
        story = [k for k, o in options.items() if o.get("story")]
        if story:
            return story[0], "story"
        if self.weak(team, step) and "grass" in options:
            return "grass", "train"
        toward = [k for k, o in options.items() if o.get("toward")] or \
            [k for k, o in options.items() if o.get("around")]
        if toward:
            pick = min(toward, key=lambda k: self.exit_rank(f, options[k]))
            return pick, options[pick].get("toward") or options[pick]["around"]
        return None, ""

    def fallback(self, m, f, options):
        """What it does if the model can't say: heal if badly hurt, else toward the goal, else look around."""
        team = party(m, self.rom)
        if hurt(team) > HEAL_AT:
            for k, o in options.items():
                if o.get("heal"):
                    return k
        goal = [k for k, o in options.items() if o.get("toward") or o.get("story")]
        if goal:
            return goal[0]
        for k in ("explore", "grass"):
            if k in options and random.random() < 0.7:
                return k
        return random.choice(list(options))

    def options(self, m, f, step=None, team=None):
        """{key: {words, kind, ...}}: what's within reach, the model's choices: the story's thing to do here (if
        it's here), doors and roads (those toward where it's heading marked so), people, trainers and items,
        obstacles a field move clears, the water, tall grass, and places not yet seen."""
        step = step or self.step(m)
        team = party(m, self.rom) if team is None else team
        doors = {(x, y) for x, y, _ in f.warps}
        seen_map, tiles = f.reach(avoid=doors)
        out = {}
        why, place = self.aim(m, f, team, step)
        dist = self.goal_distances(place)
        here_d = dist.get(f.where)
        heading = {"story": "toward your goal", "heal": "toward a Pokémon Center",
                   "train": "toward tall grass, to train"}[why]
        recently = {k for (where, k), t in self.tried.items() if where == f.where and time.monotonic() - t < TRIED_FOR}
        knows = {mv for p in team for mv, _ in p["moves"]}

        def closer(to):                          # (a way toward where it's heading: its map nearer, or there)
            there = dist.get(to)
            return there is not None and (here_d is None or there < here_d)
        # the story's thing to do here: someone to talk to, something to look at (a clock...), or a place to walk to
        tile = step["script"] if isinstance(step["script"], tuple) else None
        if tile and step["place"] == f.name:
            x, y = tile[1] + MAP_OFFSET, tile[2] + MAP_OFFSET
            if (x, y) in tiles and (x, y) != (f.x, f.y):
                out["story"] = {"words": f"{step['does']} ({way(x - f.x, y - f.y)}, {tiles[(x, y)][0]} steps): the "
                                         f"story's next step", "kind": "spot", "target": (x, y), "story": True,
                                "steps": tiles[(x, y)][0]}
        elif step["script"]:
            for p in f.people:
                spot = self.talk_spot(f, p, tiles) if f.script_of(p) == step["script"] else None
                if spot is not None:
                    out["story"] = {"words": f"{step['does']} ({way(p['x'] - f.x, p['y'] - f.y)}, "
                                             f"{tiles[spot[:2]][0]} steps): the story's next step", "kind": "talk",
                                    "person": p["local_id"], "target": spot, "story": True,
                                    "steps": tiles[spot[:2]][0]}
                    break
            for x, y, facing, script in f.signs:
                spot = self.look_spot(f, x, y, facing, tiles) if script == step["script"] and "story" not in out \
                    else None
                if spot is not None:
                    out["story"] = {"words": f"{step['does']} ({way(x - f.x, y - f.y)}, {tiles[spot[:2]][0]} "
                                             f"steps): the story's next step", "kind": "look", "target": spot,
                                    "story": True, "steps": tiles[spot[:2]][0]}
        # doors, stairs, exits
        for i, (x, y, to) in enumerate(f.warps):
            if to == (127, 127):                   # (back where you came in from: the moving truck, out to town)
                to = self.rom.by_name.get("Littleroot Town", to) if f.name == "Inside Of Truck" else f.came_from
            name = self.rom.map_name(*to)
            target = self.warp_approach(f, x, y, tiles)
            if target is None:
                continue
            steps = tiles[target[:2]][0]
            toward = why if closer(to) else ""
            around = why if (not toward and here_d is not None and dist.get(to) == here_d + 1
                             and self.rom.way_around(f.where, i, to)) else ""
            heal = name.endswith("Pokémon Center 1F")   # (not its upstairs)
            words = f"Go to {name} ({way(x - f.x, y - f.y)}, {steps} steps)" + (
                f" ({heading})" if toward else f" (a way round, {heading})" if around else "")
            out[f"door{i}"] = {"words": words, "kind": "door", "x": x, "y": y, "target": target, "to": to,
                               "toward": toward, "around": around, "heal": heal, "steps": steps}
        # roads on to the next map
        for d, _, to in f.roads:
            target = self.road_target(f, d, tiles)
            if target is None:
                continue
            name = self.rom.map_name(*to)
            toward = why if closer(to) else ""
            steps = tiles[target][0]
            words = f"Go {WORD[d]} to {name} ({steps} steps)" + (f" ({heading})" if toward else "")
            out[f"road{d}"] = {"words": words, "kind": "road", "dir": d, "target": target, "to": to,
                               "toward": toward, "steps": steps}
        # people, trainers, items
        people = []
        for p in f.people:
            if p["gfx"] in (GFX_CUT_TREE, GFX_ROCK, GFX_BOULDER):
                continue
            spot = self.talk_spot(f, p, tiles)
            if spot is not None:
                people.append((tiles[spot[:2]][0], p, spot))
        people.sort(key=lambda t: t[0])
        for steps, p, spot in people[:NEAREST_PEOPLE]:
            where = f"{way(p['x'] - f.x, p['y'] - f.y)}, {steps} steps"
            if p["gfx"] == GFX_ITEM_BALL:
                words = f"Pick up the item ({where})"
            elif p["gfx"] == GFX_NURSE:
                words = f"Talk to the nurse: she heals your Pokémon ({where})"
            elif p["trainer_type"] and f.trainer_flag(p) is not None:
                words = f"Battle the trainer ({where})"
            else:
                words = f"Talk to the person ({where})"
            out[f"talk{p['local_id']}"] = {"words": words, "kind": "talk", "person": p["local_id"], "target": spot,
                                           "heal": p["gfx"] == GFX_NURSE, "steps": steps}
        # obstacles a field move clears
        for p in f.people:
            gfx = p["gfx"]
            need = {GFX_CUT_TREE: (15, 0, "Cut down the small tree"),
                    GFX_ROCK: (249, 2, "Smash the cracked rock")}.get(gfx)
            if need and need[0] in knows and m.flag(FLAG_BADGE[need[1]]):
                spot = self.talk_spot(f, p, tiles)
                if spot is not None:
                    out[f"clear{p['local_id']}"] = {"words": f"{need[2]} ({way(p['x'] - f.x, p['y'] - f.y)})",
                                                    "kind": "talk", "person": p["local_id"], "target": spot}
        # surfing
        if 57 in knows and m.flag(FLAG_BADGE[4]) and not f.surfing:
            shore = self.shore(f, tiles)
            if shore is not None:
                out["surf"] = {"words": f"Surf on the water ({way(shore[0] - f.x, shore[1] - f.y)})",
                               "kind": "surf", "target": shore}
        # tall grass
        grass = self.nearest(f, tiles, lambda x, y: f.behaviour(x, y) in GRASS)
        if grass is not None:
            out["grass"] = {"words": "Walk in the tall grass to find wild Pokémon (to train or catch)",
                            "kind": "grass", "target": grass}
        # places not seen yet
        seen = self.seen.get(f.where, set())
        unseen = self.nearest(f, tiles, lambda x, y: f.inside(x, y) and (x, y) not in seen)
        if unseen is not None:
            out["explore"] = {"words": f"Explore the parts of {f.name} you haven't seen yet "
                                       f"({way(unseen[0] - f.x, unseen[1] - f.y)})", "kind": "explore",
                              "target": unseen}
        return {k: o for k, o in out.items() if k not in recently} or out

    def goal_distances(self, place):
        if place not in self.goal_cache:
            goal = self.rom.by_name.get(place) if place else None
            self.goal_cache[place] = self.rom.distances_to(goal) if goal else {}
        return self.goal_cache[place]

    def nearest(self, f, tiles, want):
        best = None
        for (x, y), (steps, _) in tiles.items():
            if (x, y) != (f.x, f.y) and want(x, y) and (best is None or steps < tiles[best][0]):
                best = (x, y)
        return best

    def warp_approach(self, f, x, y, tiles):
        """How to go through the door at (x, y): (where to stand, x and y; a step to take first, or None; the way
        to hold until the map changes), or None (it can't be got to)."""
        b = f.behaviour(x, y)
        if b == MB_ANIMATED_DOOR:                  # a door you walk up into: from below it
            return (x, y + 1, None, NORTH) if (x, y + 1) in tiles else None
        arrow = MB_ARROW_WARP.get(b)               # a mat you stand on, then walk off the way it points
        if arrow and (x, y) == (f.x, f.y):
            return (x, y, None, arrow)
        best = None                                # stairs, ladders, a cave's mouth: step onto it (and a mat: on,
        for d, (dx, dy) in STEP.items():           # then its way)
            n = (x - dx, y - dy)
            if n in tiles and (best is None or tiles[n][0] < tiles[best[:2]][0]):
                best = (n[0], n[1], d if arrow and arrow != d else None, arrow or d)
        return best

    def road_target(self, f, d, tiles):
        """The nearest tile you can reach off this map's edge in that direction (onto the next map)."""
        best = None
        for (x, y), (steps, _) in tiles.items():
            off = ((d == NORTH and y < MAP_OFFSET) or (d == SOUTH and y >= MAP_OFFSET + f.lh)
                   or (d == WEST and x < MAP_OFFSET) or (d == EAST and x >= MAP_OFFSET + f.lw))
            if off and (best is None or steps < tiles[best][0]):
                best = (x, y)
        return best

    def talk_spot(self, f, p, tiles):
        """Where to stand to talk to someone, and which way to face: next to them, or across a counter."""
        best = None
        for d, (dx, dy) in STEP.items():
            for far in (1, 2):
                sx, sy = p["x"] - dx * far, p["y"] - dy * far
                if far == 2 and f.behaviour(p["x"] - dx, p["y"] - dy) != MB_COUNTER:
                    continue
                if (sx, sy) in tiles and (best is None or tiles[(sx, sy)][0] < tiles[best[:2]][0]):
                    best = (sx, sy, d)
        return best

    def look_spot(self, f, x, y, facing, tiles):
        """Where to stand to look at something (a clock on the wall, a sign), and which way to face: next to it,
        facing it (from the one side it's seen from, if it's that kind)."""
        best = None
        for d, (dx, dy) in STEP.items():
            if facing and d != facing:
                continue
            sx, sy = x - dx, y - dy
            if (sx, sy) in tiles and (best is None or tiles[(sx, sy)][0] < tiles[best[:2]][0]):
                best = (sx, sy, d)
        return best

    def shore(self, f, tiles):
        """The nearest place to start surfing from: on land, facing water the game lets you surf on (lower than
        the land, and nothing in the way), and which way it is."""
        for (x, y), (_, s) in sorted(tiles.items(), key=lambda t: t[1][0]):
            if s[2] != LAND or s[3]:
                continue
            for d, (dx, dy) in STEP.items():
                b = f.block(x + dx, y + dy)
                if (f.behaviour(x + dx, y + dy) in MB_SURFABLE and not (b >> 10) & 3
                        and b >> 12 not in (0, LAND, 15)):
                    return (x, y, d)
        return None

    # -- doing it ----------------------------------------------------------------------------------------------------
    def carry_out(self, f, o):
        """Walks to where the choice is done, and does it: True if it went as it should (False: not offered
        again here for a while)."""
        kind, target = o["kind"], o["target"]
        got = self.walk_to(target[0], target[1], roads=kind == "road")
        if kind == "road":
            return got in ("here", "map")
        if got == "stopped":                       # (a battle, someone talking: the main loop sees to it)
            return True
        if got != "here":
            return False
        if kind == "door":
            layout = f.layout_id
            if target[2] is not None:              # (onto a mat from the side: then its way)
                if self.follow(Field(self.io.snapshot(), self.rom), [target[2]]) != "done":
                    return False
            return self.through(target[3], layout)
        if kind in ("talk", "look", "surf"):
            self.face(target[2])
            self.io.tap("a")
            self.io.wait(0.5)
            return True
        if kind == "grass":
            self.pace()
        return True

    def where(self):
        """(x, y, the map's layout, free to walk, a step under way) now, from a quick look."""
        got = self.io.peek((G_PLAYER_AVATAR, 6), (G_OBJECT_EVENTS, OBJECT_EVENT_SIZE * OBJECT_EVENTS),
                           (G_MAP_HEADER + 0x12, 2), (G_MAIN + 4, 4), (S_FIELD_MESSAGE_BOX_MODE, 1),
                           (S_LOCK_FIELD_CONTROLS, 1))
        if got is None or any(g is None for g in got):
            return None
        avatar, objs, layout, cb2, msg, lock = got
        a = OBJECT_EVENT_SIZE * avatar[5]
        x, y = struct.unpack_from("<hh", objs, a + 0x10)
        free = code(struct.unpack("<I", cb2)[0]) == CB2_OVERWORLD and not msg[0] and not lock[0]
        return x, y, struct.unpack("<H", layout)[0], free, bool(avatar[3])

    def walk_to(self, tx, ty, roads=False, tries=TALK_TRIES):
        """Walks there, a step at a time, watching: "here"; "map" (onto another map: a road's end); "stopped"
        (a battle, someone talking: the main loop sees to it); or "no" (blocked, or no way there)."""
        for _ in range(tries):
            m = self.io.snapshot()
            if self.mode(m)[0] != "walk":
                return "stopped"
            f = Field(m, self.rom)
            if (f.x, f.y) == (tx, ty):
                return "here"
            seen, tiles = f.reach(avoid={(x, y) for x, y, _ in f.warps} - {(tx, ty)})
            steps = f.path(seen, tiles, tx, ty)
            if steps is None:
                return "no"
            got = self.follow(f, steps)
            if got == "done":
                return "here"
            if got in ("map", "stopped"):
                return got
        return "no"

    def follow(self, f, steps):
        """The steps, a button held down for each: "done" once all are taken, the last one over (the game takes
        A, and a turn, only from standing); "map" if it came onto another map; "stopped" if something came up (a
        battle, a message); "blocked" if a step didn't happen. (A step's begun once you're on the next tile: the
        next button's held from then on, so the walk doesn't stop between them.)"""
        x, y, layout = f.x, f.y, f.layout_id
        for d in steps:
            dx, dy = STEP[d]
            jump = MB_JUMP.get(f.behaviour(x + dx, y + dy)) == d
            want = (x + 2 * dx, y + 2 * dy) if jump else (x + dx, y + dy)
            self.io.hold(BUTTON[d])
            got = "blocked"
            end = time.monotonic() + STEP_TIME * (2 if jump else 1)
            try:
                while time.monotonic() < end:
                    self.io.wait(0.03)
                    now = self.where()
                    if now is None:
                        got = "stopped"
                        break
                    if now[2] != layout:
                        got = "map"
                        break
                    if not now[3]:
                        got = "stopped"
                        break
                    if (now[0], now[1]) == want:
                        got = "done"
                        break
            finally:
                self.io.release(BUTTON[d])
            if got != "done":
                return got
            x, y = want
        return self.settle(layout) if steps else "done"

    def settle(self, layout, most=1.0):
        """Waits out the step under way, to standing: "done" (or "map", "stopped": as follow() says)."""
        end = time.monotonic() + most
        while True:
            now = self.where()
            if now is None or not now[3]:
                return "stopped"
            if now[2] != layout:
                return "map"
            if not now[4] or time.monotonic() > end:
                return "done"
            self.io.wait(0.03)

    def face(self, d):
        """Turns to face d (a quick tap turns without stepping)."""
        self.io.tap(BUTTON[d])
        self.io.wait(0.15)

    def through(self, d, layout):
        """Through a door, off a mat, onto the stairs: holds the way in until the map changes."""
        self.io.hold(BUTTON[d])
        end = time.monotonic() + WARP_TIME
        gone = False
        while time.monotonic() < end:
            self.io.wait(0.1)
            now = self.where()
            if now is None or now[2] != layout:
                gone = True
                break
        self.io.release(BUTTON[d])
        self.io.wait(0.5)
        return gone

    def pace(self):
        """Back and forth in the grass until a wild Pokémon comes (or a while's gone by)."""
        f = Field(self.io.snapshot(), self.rom)
        for d in (EAST, WEST, NORTH, SOUTH):
            nxt = f.step(f.x, f.y, f.elev, d, f.occupied(), set(), f.surfing)
            if nxt is not None and f.behaviour(nxt[0], nxt[1]) in GRASS:
                for k in range(GRASS_STEPS):
                    m = self.io.snapshot()
                    if self.mode(m)[0] != "walk":
                        return
                    if self.follow(Field(m, self.rom), [d if k % 2 == 0 else OPPOSITE[d]]) != "done":
                        return
                return

    def wander(self, f):
        """Nothing to choose from: a few steps any way it can."""
        d = random.choice((NORTH, SOUTH, WEST, EAST))
        self.follow(f, [d])
        self.io.wait(0.2)


def describe(m, rom):
    """A one-line look at the game (for the log, and the tests)."""
    try:
        f = Field(m, rom)
        return json.dumps({"map": f.name, "x": f.x - MAP_OFFSET, "y": f.y - MAP_OFFSET, "people": len(f.people)})
    except BadAddress as ex:
        return f"(unreadable: {ex})"
