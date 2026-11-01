"""Achievements (RetroAchievements) while a game plays, through rcheevos's rc_client: its librcheevos.so (setup.sh
builds it, with native/rcheevos_glue.c in it) loaded with ctypes, in the game's own process (pitato/emulator.py).

Pure Python besides: ctypes, urllib, threading. Built and tested against rcheevos 12.5.0 (and 12.2.0); its structs'
layouts are checked as it loads against the table compiled into librcheevos.so, so another rcheevos, or a 32-bit
Pi's time_t, stops it with an error instead of reading the wrong memory.

In the game's process:

    lib = RCheevos(path)
    rac = RAClient(lib, user_agent=make_user_agent("Pietato", "1.1", core_path))
    rac.on_achievement_triggered = lambda a: ...
    rac.login_token(user, token)
    rac.memory.get_memory = lambda kind: (pointer, size)        # (retro_get_memory_data and _size)
    rac.set_memory_map(descriptors)                              # (a copy of the core's SET_MEMORY_MAPS)
    rac.load_game(console_id, data=rom_bytes)                    # or path= for a disc, or an arcade game's zip
    while playing:
        rac.idle() if paused else (core.retro_run(), rac.do_frame())
    rac.close()

The asking of RetroAchievements happens on threads of its own; its answers are handed to rcheevos on the thread that
calls do_frame(), idle() or pump(), so every rcheevos callback, event and memory read is on the game's.
"""

from __future__ import annotations

import ctypes as C
import json
import logging
import os
import platform
import re
import http.client
import queue
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any, Callable, Optional

log = logging.getLogger("pitato.rcheevos")
rc_log = logging.getLogger("pitato.rcheevos.rc")

# --------------------------------------------------------------------------
# constants (rc_consoles.h, rc_client.h, rc_error.h, rc_api_request.h, libretro.h)
# --------------------------------------------------------------------------

RC_CONSOLE_MEGA_DRIVE = 1
RC_CONSOLE_NINTENDO_64 = 2
RC_CONSOLE_SUPER_NINTENDO = 3
RC_CONSOLE_GAMEBOY = 4
RC_CONSOLE_GAMEBOY_ADVANCE = 5
RC_CONSOLE_GAMEBOY_COLOR = 6
RC_CONSOLE_NINTENDO = 7
RC_CONSOLE_MASTER_SYSTEM = 11
RC_CONSOLE_PLAYSTATION = 12
RC_CONSOLE_NEOGEO_POCKET = 14
RC_CONSOLE_GAME_GEAR = 15
RC_CONSOLE_GAMECUBE = 16
RC_CONSOLE_NINTENDO_DS = 18
RC_CONSOLE_WII = 19
RC_CONSOLE_PLAYSTATION_2 = 21
RC_CONSOLE_ARCADE = 27
RC_CONSOLE_DREAMCAST = 40
RC_CONSOLE_PSP = 41

RETRO_MEMORY_SAVE_RAM = 0
RETRO_MEMORY_RTC = 1
RETRO_MEMORY_SYSTEM_RAM = 2
RETRO_MEMORY_VIDEO_RAM = 3

RC_OK = 0
RC_INVALID_STATE = -25
RC_API_FAILURE = -27
RC_LOGIN_REQUIRED = -28
RC_NO_GAME_LOADED = -29
RC_ABORTED = -31
RC_NO_RESPONSE = -32
RC_ACCESS_DENIED = -33
RC_INVALID_CREDENTIALS = -34
RC_EXPIRED_TOKEN = -35
RC_NOT_FOUND = -39
LOGIN_REQUIRED_RESULTS = (RC_LOGIN_REQUIRED, RC_ACCESS_DENIED, RC_INVALID_CREDENTIALS, RC_EXPIRED_TOKEN)

RC_API_SERVER_RESPONSE_CLIENT_ERROR = -1            # not retried by rc_client
RC_API_SERVER_RESPONSE_RETRYABLE_CLIENT_ERROR = -2  # retried (unlocks/leaderboard entries)

RC_CLIENT_LOG_LEVEL_NONE, RC_CLIENT_LOG_LEVEL_ERROR, RC_CLIENT_LOG_LEVEL_WARN, \
    RC_CLIENT_LOG_LEVEL_INFO, RC_CLIENT_LOG_LEVEL_VERBOSE = range(5)

RC_CLIENT_ACHIEVEMENT_CATEGORY_CORE = 1
RC_CLIENT_ACHIEVEMENT_CATEGORY_UNOFFICIAL = 2
RC_CLIENT_ACHIEVEMENT_LIST_GROUPING_LOCK_STATE = 0
RC_CLIENT_ACHIEVEMENT_UNLOCKED_SOFTCORE = 1
RC_CLIENT_ACHIEVEMENT_UNLOCKED_HARDCORE = 2
RC_CLIENT_ACHIEVEMENT_WARNING_ID = 101000001  # server-injected "Warning: Unknown Emulator" entry

ACHIEVEMENT_STATES = {0: "inactive", 1: "active", 2: "unlocked", 3: "disabled"}
ACHIEVEMENT_BUCKETS = {0: "unknown", 1: "locked", 2: "unlocked", 3: "unsupported", 4: "unofficial",
                       5: "recently_unlocked", 6: "active_challenge", 7: "almost_there", 8: "unsynced"}
ACHIEVEMENT_TYPES = {0: "standard", 1: "missable", 2: "progression", 3: "win"}
LOAD_STATES = {0: "none", 1: "await_login", 2: "identifying", 3: "fetching", 4: "starting_session",
               5: "done", 6: "aborted"}

EV_ACHIEVEMENT_TRIGGERED = 1
EV_LEADERBOARD_STARTED, EV_LEADERBOARD_FAILED, EV_LEADERBOARD_SUBMITTED = 2, 3, 4
EV_CHALLENGE_SHOW, EV_CHALLENGE_HIDE = 5, 6
EV_PROGRESS_SHOW, EV_PROGRESS_HIDE, EV_PROGRESS_UPDATE = 7, 8, 9
EV_TRACKER_SHOW, EV_TRACKER_HIDE, EV_TRACKER_UPDATE = 10, 11, 12
EV_LEADERBOARD_SCOREBOARD = 13
EV_RESET = 14
EV_GAME_COMPLETED = 15
EV_SERVER_ERROR = 16
EV_DISCONNECTED = 17
EV_RECONNECTED = 18
EV_SUBSET_COMPLETED = 19

# glue memory modes (native/rcheevos_glue.c)
MEM_UNAVAILABLE, MEM_DUMMY, MEM_LIVE = 0, 1, 2


class RCheevosError(RuntimeError):
    pass


def _s(value: Optional[bytes]) -> Optional[str]:
    return value.decode("utf-8", "replace") if value is not None else None


def _sb(arr) -> str:  # fixed char[N] field -> str
    return bytes(arr).split(b"\0", 1)[0].decode("utf-8", "replace")


# --------------------------------------------------------------------------
# struct layouts (exactly as in rcheevos' headers; gated on version)
# --------------------------------------------------------------------------

def _make_types(time_t, version: int) -> types.SimpleNamespace:
    u8, u32, u64, i32, sz, vp, cp, f32 = C.c_uint8, C.c_uint32, C.c_uint64, C.c_int, C.c_size_t, C.c_void_p, C.c_char_p, C.c_float
    T = types.SimpleNamespace(time_t=time_t)

    class rc_buffer_chunk_t(C.Structure):
        _fields_ = [("write", vp), ("end", vp), ("start", vp), ("next", vp)]

    class rc_buffer_t(C.Structure):
        _fields_ = [("chunk", rc_buffer_chunk_t), ("data", u8 * 256)]

    class rc_api_request_t(C.Structure):
        _fields_ = [("url", cp), ("post_data", cp), ("content_type", cp), ("buffer", rc_buffer_t)]

    class rc_api_server_response_t(C.Structure):
        _fields_ = [("body", vp), ("body_length", sz), ("http_status_code", i32)]

    user_fields = [("display_name", cp), ("username", cp), ("token", cp), ("score", u32),
                   ("score_softcore", u32), ("num_unread_messages", u32), ("avatar_url", cp)]
    if version >= 12004000:
        user_fields.append(("avatar_last_updated", time_t))

    class rc_client_user_t(C.Structure):
        _fields_ = user_fields

    class rc_client_user_game_summary_t(C.Structure):
        _fields_ = [("num_core_achievements", u32), ("num_unofficial_achievements", u32),
                    ("num_unlocked_achievements", u32), ("num_unsupported_achievements", u32),
                    ("points_core", u32), ("points_unlocked", u32),
                    ("beaten_time", time_t), ("completed_time", time_t)]

    class rc_client_game_t(C.Structure):
        _fields_ = [("id", u32), ("console_id", u32), ("title", cp), ("hash", cp),
                    ("badge_name", cp), ("badge_url", cp)]

    class rc_client_subset_t(C.Structure):
        _fields_ = [("id", u32), ("title", cp), ("badge_name", C.c_char * 16), ("num_achievements", u32),
                    ("num_leaderboards", u32), ("badge_url", cp)]

    class rc_client_achievement_t(C.Structure):
        _fields_ = [("title", cp), ("description", cp), ("badge_name", C.c_char * 8),
                    ("measured_progress", C.c_char * 24), ("measured_percent", f32), ("id", u32),
                    ("points", u32), ("unlock_time", time_t), ("state", u8), ("category", u8),
                    ("bucket", u8), ("unlocked", u8), ("rarity", f32), ("rarity_hardcore", f32),
                    ("type", u8), ("badge_url", cp), ("badge_locked_url", cp)]

    class rc_client_achievement_bucket_t(C.Structure):
        _fields_ = [("achievements", C.POINTER(C.POINTER(rc_client_achievement_t))), ("num_achievements", u32),
                    ("label", cp), ("subset_id", u32), ("bucket_type", u8)]

    class rc_client_achievement_list_t(C.Structure):
        _fields_ = [("buckets", C.POINTER(rc_client_achievement_bucket_t)), ("num_buckets", u32)]

    class rc_client_leaderboard_t(C.Structure):
        _fields_ = [("title", cp), ("description", cp), ("tracker_value", cp), ("id", u32),
                    ("state", u8), ("format", u8), ("lower_is_better", u8)]

    class rc_client_leaderboard_tracker_t(C.Structure):
        _fields_ = [("display", C.c_char * 24), ("id", u32)]

    class rc_client_leaderboard_scoreboard_entry_t(C.Structure):
        _fields_ = [("username", cp), ("rank", u32), ("score", C.c_char * 24)]

    class rc_client_leaderboard_scoreboard_t(C.Structure):
        _fields_ = [("leaderboard_id", u32), ("submitted_score", C.c_char * 24), ("best_score", C.c_char * 24),
                    ("new_rank", u32), ("num_entries", u32),
                    ("top_entries", C.POINTER(rc_client_leaderboard_scoreboard_entry_t)), ("num_top_entries", u32)]

    class rc_client_server_error_t(C.Structure):
        _fields_ = [("error_message", cp), ("api", cp), ("result", i32), ("related_id", u32)]

    class rc_client_event_t(C.Structure):
        _fields_ = [("type", u32),
                    ("achievement", C.POINTER(rc_client_achievement_t)),
                    ("leaderboard", C.POINTER(rc_client_leaderboard_t)),
                    ("leaderboard_tracker", C.POINTER(rc_client_leaderboard_tracker_t)),
                    ("leaderboard_scoreboard", C.POINTER(rc_client_leaderboard_scoreboard_t)),
                    ("server_error", C.POINTER(rc_client_server_error_t)),
                    ("subset", C.POINTER(rc_client_subset_t))]

    class rc_memory_region_t(C.Structure):
        _fields_ = [("start_address", u32), ("end_address", u32), ("real_address", u32), ("type", u8),
                    ("description", cp)]

    class rc_memory_regions_t(C.Structure):
        _fields_ = [("region", C.POINTER(rc_memory_region_t)), ("num_regions", u32)]

    class rc_libretro_memory_regions_t(C.Structure):  # RC_LIBRETRO_MAX_MEMORY_REGIONS = 32
        _fields_ = [("data", vp * 32), ("size", sz * 32), ("total_size", sz), ("count", u32)]

    class rc_libretro_core_memory_info_t(C.Structure):
        _fields_ = [("data", vp), ("size", sz)]

    class retro_memory_descriptor(C.Structure):  # libretro.h
        _fields_ = [("flags", u64), ("ptr", vp), ("offset", sz), ("start", sz), ("select", sz),
                    ("disconnect", sz), ("len", sz), ("addrspace", cp)]

    class retro_memory_map(C.Structure):
        _fields_ = [("descriptors", C.POINTER(retro_memory_descriptor)), ("num_descriptors", C.c_uint)]

    class ra_memory_t(C.Structure):  # native/rcheevos_glue.c
        _fields_ = [("regions", C.POINTER(rc_libretro_memory_regions_t)), ("mode", u32)]

    # rc_hash.h, built without RC_HASH_NO_DISC / RC_HASH_NO_ENCRYPTED (build.sh); all function pointers
    class rc_hash_filereader_t(C.Structure):
        _fields_ = [("open", vp), ("seek", vp), ("tell", vp), ("read", vp), ("close", vp)]

    class rc_hash_cdreader_t(C.Structure):
        _fields_ = [("open_track", vp), ("read_sector", vp), ("close_track", vp), ("first_track_sector", vp),
                    ("open_track_iterator", vp)]

    class rc_hash_encryption_callbacks(C.Structure):
        _fields_ = [("get_3ds_cia_normal_key", vp), ("get_3ds_ncch_normal_keys", vp)]

    class rc_hash_callbacks_t(C.Structure):
        _fields_ = [("verbose_message", vp), ("error_message", vp), ("filereader", rc_hash_filereader_t),
                    ("cdreader", rc_hash_cdreader_t), ("encryption", rc_hash_encryption_callbacks)]

    for k, v in list(locals().items()):
        if isinstance(v, type) and issubclass(v, C.Structure):
            setattr(T, k, v)

    # callback types (RC_CCONV is cdecl / default everywhere we run)
    T.READ_MEMORY = C.CFUNCTYPE(u32, u32, C.POINTER(u8), u32, vp)
    T.SERVER_CALLBACK = C.CFUNCTYPE(None, C.POINTER(rc_api_server_response_t), vp)
    T.SERVER_CALL = C.CFUNCTYPE(None, C.POINTER(rc_api_request_t), vp, vp, vp)
    T.CLIENT_CALLBACK = C.CFUNCTYPE(None, i32, cp, vp, vp)
    T.MESSAGE_CALLBACK = C.CFUNCTYPE(None, cp, vp)
    T.EVENT_HANDLER = C.CFUNCTYPE(None, C.POINTER(rc_client_event_t), vp)
    T.GET_TIME = C.CFUNCTYPE(u64, vp)
    T.GET_CORE_MEMORY_INFO = C.CFUNCTYPE(None, u32, C.POINTER(rc_libretro_core_memory_info_t))
    T.LIBRETRO_MESSAGE = C.CFUNCTYPE(None, cp)
    T.LIST_CALLBACK = C.CFUNCTYPE(None, i32, cp, vp, vp, vp)  # (result, msg, list*, client, userdata)
    T.FR_OPEN = C.CFUNCTYPE(vp, cp)
    T.FR_SEEK = C.CFUNCTYPE(None, vp, C.c_int64, i32)
    T.FR_TELL = C.CFUNCTYPE(C.c_int64, vp)
    T.FR_READ = C.CFUNCTYPE(sz, vp, vp, sz)
    T.FR_CLOSE = C.CFUNCTYPE(None, vp)
    return T


class _AbiEntry(C.Structure):
    _fields_ = [("name", C.c_char_p), ("value", C.c_size_t)]


class _ListHead(C.Structure):
    _fields_ = [("entries", C.c_void_p), ("num_entries", C.c_uint32)]


def _fnaddr(cfunc) -> int:
    """Address of a ctypes CFUNCTYPE object (pass as a C function pointer)."""
    return C.cast(cfunc, C.c_void_p).value


class RCheevos:
    """The loaded librcheevos.so, its ctypes prototypes and struct types (lib.T)."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get("PITATO_RCHEEVOS") or "/usr/local/lib/pitato/librcheevos.so"
        self.dll = C.CDLL(self.path)  # RTLD_LOCAL: keeps rc_* out of the global namespace
        self.dll.rc_version.restype = C.c_uint32
        self.dll.rc_version_string.restype = C.c_char_p
        self.version = int(self.dll.rc_version())
        self.version_string = self.dll.rc_version_string().decode()
        if self.version < 12000000:
            raise RCheevosError(f"rcheevos {self.version_string} is too old (need >= 12.0)")

        self.abi = self._read_abi()
        if self.abi:
            tsize = self.abi["sizeof:time_t"]
            time_t = {4: C.c_int32, 8: C.c_int64}[tsize]
            if self.abi.get("rcheevos_version") not in (None, self.version):
                raise RCheevosError("rcheevos_glue.c was compiled against different rcheevos headers")
        else:  # no rcheevos_glue.c compiled in: best guess
            time_t = getattr(C, "c_time_t", C.c_long)
            log.warning("librcheevos.so has no ra_abi_table; struct layouts not verified")
        self.T = _make_types(time_t, self.version)
        if self.abi:
            self._check_abi()
        self._prototypes()
        self.has_glue = hasattr(self, "ra_read_memory")

    # ---- ABI verification ----
    def _read_abi(self) -> dict:
        try:
            fn = self.dll.ra_abi_table
        except AttributeError:
            return {}
        fn.restype = C.POINTER(_AbiEntry)
        table, out, i = fn(), {}, 0
        while table[i].name is not None:
            out[table[i].name.decode()] = int(table[i].value)
            i += 1
        return out

    def _check_abi(self) -> None:
        errors = []
        for key, value in self.abi.items():
            if key.startswith("sizeof:"):
                name = key[7:].replace("struct ", "")
                if name in ("time_t", "size_t", "void*", "int", "long"):
                    py = {"time_t": C.sizeof(self.T.time_t), "size_t": C.sizeof(C.c_size_t),
                          "void*": C.sizeof(C.c_void_p), "int": C.sizeof(C.c_int), "long": C.sizeof(C.c_long)}[name]
                else:
                    py = C.sizeof(getattr(self.T, name))
                if py != value:
                    errors.append(f"sizeof({name}) C={value} ctypes={py}")
            elif "." in key:
                sname, field = key.replace("struct ", "").split(".", 1)
                cls = getattr(self.T, sname, None)
                off = getattr(cls, field).offset if cls is not None and hasattr(cls, field) else None
                if off != value:
                    errors.append(f"offsetof({sname}.{field}) C={value} ctypes={off}")
        if errors:
            raise RCheevosError("struct layout mismatch with librcheevos.so:\n  " + "\n  ".join(errors))

    # ---- prototypes ----
    def _fn(self, name, restype, *argtypes, optional=False):
        try:
            f = getattr(self.dll, name)
        except AttributeError:
            if optional:
                return
            raise
        f.restype = restype
        f.argtypes = list(argtypes)
        setattr(self, name, f)

    def _prototypes(self) -> None:
        T, vp, cp, i, u32, sz = self.T, C.c_void_p, C.c_char_p, C.c_int, C.c_uint32, C.c_size_t
        P = C.POINTER
        fn = self._fn
        fn("rc_error_str", cp, i)
        fn("rc_console_name", cp, u32)
        fn("rc_console_memory_regions", P(T.rc_memory_regions_t), u32)
        fn("rc_client_create", vp, vp, vp)
        fn("rc_client_destroy", None, vp)
        fn("rc_client_set_hardcore_enabled", None, vp, i)
        fn("rc_client_get_hardcore_enabled", i, vp)
        fn("rc_client_set_unofficial_enabled", None, vp, i)
        fn("rc_client_set_encore_mode_enabled", None, vp, i)
        fn("rc_client_set_spectator_mode_enabled", None, vp, i)
        fn("rc_client_set_userdata", None, vp, vp)
        fn("rc_client_get_userdata", vp, vp)
        fn("rc_client_set_host", None, vp, cp)
        fn("rc_client_set_get_time_millisecs_function", None, vp, vp)
        fn("rc_client_abort_async", None, vp, vp)
        fn("rc_client_get_user_agent_clause", sz, vp, P(C.c_char), sz)
        fn("rc_client_enable_logging", None, vp, i, vp)
        fn("rc_client_begin_login_with_password", vp, vp, cp, cp, vp, vp)
        fn("rc_client_begin_login_with_token", vp, vp, cp, cp, vp, vp)
        fn("rc_client_logout", None, vp)
        fn("rc_client_get_user_info", P(T.rc_client_user_t), vp)
        fn("rc_client_get_user_game_summary", None, vp, P(T.rc_client_user_game_summary_t))
        fn("rc_client_begin_identify_and_load_game", vp, vp, u32, cp, vp, sz, vp, vp)
        fn("rc_client_begin_load_game", vp, vp, cp, vp, vp)
        fn("rc_client_get_load_game_state", i, vp)
        fn("rc_client_is_game_loaded", i, vp)
        fn("rc_client_unload_game", None, vp)
        fn("rc_client_get_game_info", P(T.rc_client_game_t), vp)
        fn("rc_client_begin_identify_and_change_media", vp, vp, cp, vp, sz, vp, vp)
        fn("rc_client_begin_change_media", vp, vp, cp, vp, vp)
        fn("rc_client_get_achievement_info", P(T.rc_client_achievement_t), vp, u32)
        fn("rc_client_create_achievement_list", P(T.rc_client_achievement_list_t), vp, i, i)
        fn("rc_client_destroy_achievement_list", None, P(T.rc_client_achievement_list_t))
        fn("rc_client_has_achievements", i, vp)
        fn("rc_client_has_rich_presence", i, vp)
        fn("rc_client_get_rich_presence_message", sz, vp, P(C.c_char), sz)
        fn("rc_client_set_event_handler", None, vp, vp)
        fn("rc_client_set_read_memory_function", None, vp, vp)
        fn("rc_client_set_allow_background_memory_reads", None, vp, i)
        fn("rc_client_is_processing_required", i, vp)
        fn("rc_client_do_frame", None, vp)
        fn("rc_client_idle", None, vp)
        fn("rc_client_can_pause", i, vp, P(u32))
        fn("rc_client_reset", None, vp)
        fn("rc_client_progress_size", sz, vp)
        fn("rc_client_serialize_progress_sized", i, vp, vp, sz)
        fn("rc_client_deserialize_progress_sized", i, vp, vp, sz)
        # list fetchers (only used by the tests to validate the fake server's JSON)
        fn("rc_client_begin_fetch_hash_library", vp, vp, u32, vp, vp)
        fn("rc_client_destroy_hash_library", None, vp)
        fn("rc_client_begin_fetch_game_titles", vp, vp, P(u32), u32, vp, vp)
        fn("rc_client_destroy_game_title_list", None, vp)
        fn("rc_client_begin_fetch_all_user_progress", vp, vp, u32, vp, vp)
        fn("rc_client_destroy_all_user_progress", None, vp)
        fn("rc_client_begin_fetch_leaderboard_entries", vp, vp, u32, u32, u32, vp, vp)
        fn("rc_client_destroy_leaderboard_entry_list", None, vp)
        fn("rc_client_begin_fetch_game_list", vp, vp, u32, vp, vp, optional=True)  # 12.4+
        fn("rc_client_destroy_game_list", None, vp, optional=True)
        # rc_libretro
        fn("rc_libretro_memory_init", i, P(T.rc_libretro_memory_regions_t), P(T.retro_memory_map), vp, u32)
        fn("rc_libretro_memory_destroy", None, P(T.rc_libretro_memory_regions_t))
        fn("rc_libretro_memory_find", vp, P(T.rc_libretro_memory_regions_t), u32)
        fn("rc_libretro_memory_read", u32, P(T.rc_libretro_memory_regions_t), u32, vp, u32)
        fn("rc_libretro_init_verbose_message_callback", None, vp)
        fn("rc_libretro_get_disallowed_settings", vp, cp)
        fn("rc_libretro_get_disallowed_settings_for_system", vp, cp, u32, optional=True)  # 12.5+
        fn("rc_libretro_is_setting_allowed", i, vp, cp, cp)
        fn("rc_libretro_is_system_allowed", i, cp, u32)
        fn("rc_client_set_hash_callbacks", None, vp, P(T.rc_hash_callbacks_t))
        # rc_hash (deprecated one-shot helpers; fine for tooling/tests)
        fn("rc_hash_generate_from_buffer", i, P(C.c_char), u32, vp, sz)
        fn("rc_hash_generate_from_file", i, P(C.c_char), u32, cp)
        # rcheevos_glue.c
        fn("ra_read_memory", u32, u32, P(C.c_uint8), u32, vp, optional=True)

    # ---- small helpers ----
    def error_str(self, code: int) -> str:
        return _s(self.rc_error_str(code)) or str(code)

    def console_name(self, console_id: int) -> str:
        return _s(self.rc_console_name(console_id)) or str(console_id)

    def console_regions(self, console_id: int) -> list[dict]:
        p = self.rc_console_memory_regions(console_id)
        if not p:
            return []
        regs = p.contents
        return [dict(start=regs.region[k].start_address, end=regs.region[k].end_address,
                     real=regs.region[k].real_address, type=regs.region[k].type,
                     description=_s(regs.region[k].description)) for k in range(regs.num_regions)]

    def hash_buffer(self, console_id: int, data: bytes) -> Optional[str]:
        out = C.create_string_buffer(33)
        ptr, size, _keep = _buffer_pointer(data)
        return out.value.decode() if self.rc_hash_generate_from_buffer(out, console_id, ptr, size) else None

    def hash_file(self, console_id: int, path: str) -> Optional[str]:
        out = C.create_string_buffer(33)
        return out.value.decode() if self.rc_hash_generate_from_file(out, console_id, os.fsencode(path)) else None

    def is_setting_allowed(self, library_name: str, setting: str, value: str, console_id: int = 0) -> bool:
        """Hardcore helper: rc_libretro's per-core list of disallowed core options."""
        if console_id and hasattr(self, "rc_libretro_get_disallowed_settings_for_system"):
            table = self.rc_libretro_get_disallowed_settings_for_system(library_name.encode(), console_id)
            if table and not self.rc_libretro_is_setting_allowed(table, setting.encode(), value.encode()):
                return False
        table = self.rc_libretro_get_disallowed_settings(library_name.encode())
        return not table or bool(self.rc_libretro_is_setting_allowed(table, setting.encode(), value.encode()))


def _buffer_pointer(data) -> tuple[Optional[int], int, Any]:
    """(address, size, keepalive) for bytes / bytearray / memoryview / numpy / ctypes buffers, without copying."""
    if data is None:
        return None, 0, None
    if isinstance(data, bytes):
        keep = C.c_char_p(data)  # points at the bytes object's own storage
        return C.cast(keep, C.c_void_p).value, len(data), (keep, data)
    if hasattr(data, "ctypes") and hasattr(data, "nbytes"):  # numpy array
        return int(data.ctypes.data), int(data.nbytes), data
    mv = memoryview(data)
    if not mv.contiguous:
        raise ValueError("buffer must be contiguous")
    if mv.readonly:
        b = bytes(mv)
        return _buffer_pointer(b)
    arr = (C.c_uint8 * mv.nbytes).from_buffer(mv.cast("B"))
    return C.addressof(arr), mv.nbytes, (arr, data)


# --------------------------------------------------------------------------
# memory: rc_libretro_memory_init / rc_libretro_memory_read
# --------------------------------------------------------------------------

def copy_retro_memory_map(lib: RCheevos, mmap_address: int) -> list[dict]:
    """Deep-copy a `const struct retro_memory_map *` the core passed to
    RETRO_ENVIRONMENT_SET_MEMORY_MAPS.  Call it *inside* the environment callback:
    cores may pass a stack array (mGBA does)."""
    mm = C.cast(mmap_address, C.POINTER(lib.T.retro_memory_map)).contents
    out = []
    for k in range(mm.num_descriptors):
        d = mm.descriptors[k]
        out.append(dict(flags=d.flags, ptr=d.ptr or 0, offset=d.offset, start=d.start, select=d.select,
                        disconnect=d.disconnect, len=d.len, addrspace=_s(d.addrspace)))
    return out


class LibretroMemory:
    """Owns an rc_libretro_memory_regions_t built by rc_libretro_memory_init from
    (a copy of) the core's memory descriptors, or from SYSTEM_RAM/SAVE_RAM.

    get_memory(mem_id) -> (address, size): answer from retro_get_memory_data/size.
    """

    def __init__(self, lib: RCheevos, get_memory: Optional[Callable[[int], tuple[int, int]]] = None):
        self.lib = lib
        self.get_memory = get_memory
        self.regions = lib.T.rc_libretro_memory_regions_t()
        self._descs = None   # ctypes array we own
        self._strings = []   # keep addrspace strings alive
        self._mmap = None
        self.valid = False
        self.console_id = 0
        self._info_cb = lib.T.GET_CORE_MEMORY_INFO(self._get_core_memory_info)

    def set_memory_map(self, descriptors: Optional[list]) -> None:
        """descriptors: list of dicts (flags, ptr, offset, start, select, disconnect, len,
        addrspace) - e.g. from copy_retro_memory_map() - or None to forget the map."""
        if not descriptors:
            self._descs = self._mmap = None
            self._strings = []
            return
        T = self.lib.T
        arr = (T.retro_memory_descriptor * len(descriptors))()
        strings = []
        for k, d in enumerate(descriptors):
            if not isinstance(d, dict):
                d = {f: getattr(d, f) for f, _ in T.retro_memory_descriptor._fields_}
            arr[k].flags = int(d.get("flags", 0))
            arr[k].ptr = int(d.get("ptr") or 0) or None
            arr[k].offset = int(d.get("offset", 0))
            arr[k].start = int(d.get("start", 0))
            arr[k].select = int(d.get("select", 0))
            arr[k].disconnect = int(d.get("disconnect", 0))
            arr[k].len = int(d.get("len", 0))
            space = d.get("addrspace")
            if isinstance(space, str):
                space = space.encode()
            if space:
                strings.append(space)
                arr[k].addrspace = space
        self._descs, self._strings = arr, strings
        self._mmap = T.retro_memory_map(C.cast(arr, C.POINTER(T.retro_memory_descriptor)), len(descriptors))

    def _get_core_memory_info(self, mem_id, info_ptr) -> None:
        info = info_ptr.contents
        info.data, info.size = None, 0
        if self.get_memory is None:
            return
        try:
            res = self.get_memory(int(mem_id))
            if res:
                addr, size = res
                if addr and size:
                    info.data, info.size = int(addr), int(size)
        except Exception:
            log.exception("get_memory(%d) failed", mem_id)

    def init(self, console_id: int) -> bool:
        """(Re)build the regions for console_id. Returns True if any region has real memory."""
        self.console_id = console_id
        self.lib.rc_libretro_memory_destroy(C.byref(self.regions))
        mmap = C.byref(self._mmap) if self._mmap is not None else None
        self.valid = bool(self.lib.rc_libretro_memory_init(C.byref(self.regions), mmap,
                                                           _fnaddr(self._info_cb), console_id))
        return self.valid

    def destroy(self) -> None:
        self.lib.rc_libretro_memory_destroy(C.byref(self.regions))
        self.valid = False

    def read(self, address: int, num_bytes: int = 1) -> bytes:
        buf = (C.c_uint8 * num_bytes)()
        n = self.lib.rc_libretro_memory_read(C.byref(self.regions), address, buf, num_bytes)
        return bytes(buf[:n])

    def describe(self) -> list[tuple[int, int, bool]]:
        """[(rcheevos_start_address, size, has_memory)] for each registered block."""
        out, addr = [], 0
        for k in range(self.regions.count):
            size = self.regions.size[k]
            out.append((addr, size, bool(self.regions.data[k])))
            addr += size
        return out


# --------------------------------------------------------------------------
# custom file access for hashing (rc_client_set_hash_callbacks)
# --------------------------------------------------------------------------

class FileReader:
    """rc_hash_filereader_t implemented in Python.  rc_hash uses it for every file it
    opens while hashing (ROMs, .cue/.bin/.iso tracks via the default CD reader, .m3u),
    so overriding open_file() lets you serve compressed containers.  Hashing runs
    synchronously inside load_game()/change_media() on the calling thread."""

    def __init__(self):
        self._files: dict[int, Any] = {}
        self._next = 1

    def open_file(self, path: str):
        """Return a file-like object (read/seek/tell/close) or None."""
        return open(path, "rb")

    # C-facing trampolines (never raise into C)
    def _open(self, path_b):
        try:
            f = self.open_file(os.fsdecode(path_b))
        except (OSError, ValueError) as e:
            log.debug("hash reader: cannot open %r: %s", path_b, e)
            return None
        if f is None:
            return None
        h = self._next
        self._next += 1
        self._files[h] = f
        return h

    def _seek(self, h, offset, whence):
        try:
            self._files[h].seek(offset, whence)
        except Exception:
            log.exception("hash reader seek")

    def _tell(self, h):
        try:
            return self._files[h].tell()
        except Exception:
            return 0

    def _read(self, h, buf, n):
        try:
            data = self._files[h].read(n)
            C.memmove(buf, data, len(data))
            return len(data)
        except Exception:
            log.exception("hash reader read")
            return 0

    def _close(self, h):
        f = self._files.pop(h, None)
        if f is not None:
            try:
                f.close()
            except Exception:
                pass


class CsoFile:
    """Read-only view of a CISO v0/v1 (.cso, deflate) image as the plain ISO it contains.
    (PPSSPP / PCSX2 / LRPS2 load these; rc_hash needs the raw sectors.)  ZSO (LZ4) and
    CSO v2 are not handled."""

    def __init__(self, path: str):
        import struct
        import zlib
        self._zlib = zlib
        self.f = open(path, "rb")
        magic, _hsize, self.size, self.block, ver, self.align = struct.unpack("<4sIQIBB2x", self.f.read(24))
        if magic != b"CISO" or ver > 1 or not self.block:
            self.f.close()
            raise ValueError(f"not a CSO v1 file: {path}")
        nblocks = (self.size + self.block - 1) // self.block
        self.index = struct.unpack(f"<{nblocks + 1}I", self.f.read(4 * (nblocks + 1)))
        self.pos = 0
        self._cache = (-1, b"")

    def _block(self, i: int) -> bytes:
        if self._cache[0] == i:
            return self._cache[1]
        a, b = self.index[i], self.index[i + 1]
        start, end = (a & 0x7FFFFFFF) << self.align, (b & 0x7FFFFFFF) << self.align
        self.f.seek(start)
        raw = self.f.read(end - start)
        data = raw[:self.block] if a & 0x80000000 else self._zlib.decompressobj(-15).decompress(raw)
        self._cache = (i, data)
        return data

    def read(self, n: int = -1) -> bytes:
        n = self.size - self.pos if n < 0 else min(n, self.size - self.pos)
        out = bytearray()
        while n > 0:
            i, off = divmod(self.pos, self.block)
            chunk = self._block(i)[off:off + n]
            if not chunk:
                break
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = max(0, offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset)
        return self.pos

    def tell(self) -> int:
        return self.pos

    def close(self) -> None:
        self.f.close()


class CsoFileReader(FileReader):
    """FileReader that transparently decompresses .cso (PSP / PS2 ISOs)."""

    def open_file(self, path: str):
        if path.lower().endswith(".cso"):
            return CsoFile(path)
        return super().open_file(path)


_libretro_log_cb = None


def enable_libretro_memory_logging(lib: RCheevos, logger: logging.Logger = log) -> None:
    """Route rc_libretro's 'Registered 0x... bytes ...' mapping messages to logging (global setting)."""
    global _libretro_log_cb

    def cb(msg):
        logger.debug("rc_libretro: %s", _s(msg))
    _libretro_log_cb = lib.T.LIBRETRO_MESSAGE(cb)
    lib.rc_libretro_init_verbose_message_callback(_fnaddr(_libretro_log_cb))


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def make_user_agent(app_name: str, app_version: str, core_path: Optional[str] = None,
                    core_version: Optional[str] = None) -> str:
    """'App/1.2.3 (Linux 6.6.51; aarch64) mgba_libretro/0.10.3' - the rcheevos clause is
    appended by RAClient.  RetroAchievements wants a unique, stable product name with a
    numeric version (docs.retroachievements.org/general/hardcore-compliance-requirements)."""
    rel = re.split(r"[-+]", platform.release())[0]  # '6.6.51+rpt-rpi-v8' -> '6.6.51'
    ua = f"{app_name}/{app_version} ({platform.system()} {rel}; {platform.machine()})"
    if core_path:
        core = os.path.splitext(os.path.basename(core_path))[0].replace(" ", "_")
        ua += f" {core}" + (f"/{core_version.replace(' ', '_')}" if core_version else "")
    return ua


class _Job:
    __slots__ = ("url", "post", "content_type", "callback", "callback_data", "api", "submitted")

    def __init__(self, url, post, content_type, callback, callback_data):
        self.url, self.post, self.content_type = url, post, content_type
        self.callback, self.callback_data = callback, callback_data
        params = urllib.parse.parse_qs((post or b"").decode("latin-1")) if post else \
            urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.api = (params.get("r") or ["?"])[0]
        self.submitted = time.monotonic()


class _HttpWorkers:
    """Daemon worker threads doing blocking urllib POSTs; results go to `done`."""

    def __init__(self, workers: int, timeout: float, done: queue.Queue):
        self.q: queue.Queue = queue.Queue()
        self.done = done
        self.timeout = timeout
        self.user_agent = "Pietato"
        self._direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._default = urllib.request.build_opener()
        self.threads = [threading.Thread(target=self._run, name=f"ra-http-{n}", daemon=True) for n in range(workers)]
        for t in self.threads:
            t.start()

    def submit(self, job: _Job) -> None:
        self.q.put(job)

    def stop(self) -> None:
        for _ in self.threads:
            self.q.put(None)

    def _run(self) -> None:
        while True:
            job = self.q.get()
            if job is None:
                return
            status, body = self._fetch(job)
            self.done.put((job, status, body))

    def _fetch(self, job: _Job) -> tuple[int, bytes]:
        headers = {"User-Agent": self.user_agent}
        if job.post is not None:
            headers["Content-Type"] = job.content_type or "application/x-www-form-urlencoded"
        host = urllib.parse.urlsplit(job.url).hostname or ""
        opener = self._direct if host in ("localhost", "127.0.0.1", "::1") else self._default
        try:
            req = urllib.request.Request(job.url, data=job.post, headers=headers,
                                         method="POST" if job.post is not None else "GET")
            with opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:  # 4xx/5xx still carry the JSON body rcheevos wants
            try:
                body = e.read()
            except Exception:
                body = b""
            return e.code, body
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:  # refused, DNS, timeout, reset
            reason = getattr(e, "reason", e)
            return RC_API_SERVER_RESPONSE_RETRYABLE_CLIENT_ERROR, f"Network error: {reason}".encode()
        except Exception as e:  # malformed URL etc. - not worth retrying
            return RC_API_SERVER_RESPONSE_CLIENT_ERROR, f"Request failed: {e!r}".encode()


# --------------------------------------------------------------------------
# the client
# --------------------------------------------------------------------------

class RAClient:
    """rc_client wrapper for one game process.  Softcore only (hardcore is switched off
    at creation: hardcore would need save states, cheats and slow motion turned off too).

    Event hooks (assign callables; all are called on the do_frame() thread with plain
    dicts that stay valid after the call):
        on_achievement_triggered(ach)      ach: id,title,description,points,badge_name,badge_url,...
        on_progress(ach | None)            progress indicator show/update (None = hide)
        on_challenge(ach, shown: bool)     challenge indicator
        on_game_completed(info)            info: game_id,title,mastered(bool, hardcore only)
        on_subset_completed(subset)
        on_server_error(err)               err: api,message,result,related_id
        on_disconnected() / on_reconnected()
        on_login_required(reason: str)     password/token rejected, token expired, not logged in
        on_login(result, message)          after login_password/login_token
        on_game_loaded(result, message)    after load_game (RC_NO_GAME_LOADED = unknown hash)
        on_reset_requested()               rc_client wants an emulator reset (hardcore enable only)
        on_leaderboard(kind, data)         leaderboard events (not raised in softcore)
        on_event(name, data)               catch-all, called for every event above
    """

    def __init__(self, lib: Optional[RCheevos] = None, *, user_agent: str = "Pietato/1.1",
                 host: Optional[str] = None, log_level: int = RC_CLIENT_LOG_LEVEL_WARN,
                 http_timeout: float = 30.0, http_workers: int = 2, use_glue: bool = True,
                 clock_ms: Optional[Callable[[], int]] = None, memory_wait_frames: int = 300):
        self.lib = lib or RCheevos()
        T = self.lib.T
        self.T = T
        self._done: queue.Queue = queue.Queue()
        self._http = _HttpWorkers(http_workers, http_timeout, self._done)
        self.inflight: Counter = Counter()  # api -> outstanding HTTP requests
        self.disconnected = False
        self.memory = LibretroMemory(self.lib)
        self.memory_wait_frames = memory_wait_frames
        self._use_glue = use_glue and self.lib.has_glue
        self._glue = T.ra_memory_t(C.pointer(self.memory.regions), MEM_DUMMY)
        self._mem_pending = False
        self._mem_wait = 0
        self._load_console = 0
        self._pending: dict[int, tuple] = {}
        self._next_key = 1
        self._closed = False
        self._login_required_sent = False

        for name in ("on_achievement_triggered", "on_progress", "on_challenge", "on_game_completed",
                     "on_subset_completed", "on_server_error", "on_disconnected", "on_reconnected",
                     "on_login_required", "on_login", "on_game_loaded", "on_reset_requested",
                     "on_leaderboard", "on_event"):
            setattr(self, name, None)

        # ctypes callback objects must outlive the client
        self._c_server_call = T.SERVER_CALL(self._server_call)
        self._c_read_uninit = T.READ_MEMORY(self._read_uninitialized)
        self._c_read_py = T.READ_MEMORY(self._read_python)
        self._c_event = T.EVENT_HANDLER(self._event_handler)
        self._c_login_cb = T.CLIENT_CALLBACK(self._login_callback)
        self._c_load_cb = T.CLIENT_CALLBACK(self._load_callback)
        self._c_media_cb = T.CLIENT_CALLBACK(self._media_callback)
        self._c_log = T.MESSAGE_CALLBACK(self._log_message)
        self._c_list_cb = T.LIST_CALLBACK(self._list_callback)
        self._glue_read_addr = C.cast(self.lib.ra_read_memory, C.c_void_p).value if self.lib.has_glue else None

        self._client = self.lib.rc_client_create(self._fnaddr(self._c_read_uninit), self._fnaddr(self._c_server_call))
        if not self._client:
            raise RCheevosError("rc_client_create failed")
        L, c = self.lib, self._client
        L.rc_client_set_userdata(c, C.addressof(self._glue))
        L.rc_client_set_event_handler(c, self._fnaddr(self._c_event))
        L.rc_client_set_hardcore_enabled(c, 0)          # default is ON - softcore only here
        L.rc_client_set_unofficial_enabled(c, 0)
        L.rc_client_set_encore_mode_enabled(c, 0)
        if log_level > RC_CLIENT_LOG_LEVEL_NONE:
            L.rc_client_enable_logging(c, log_level, self._fnaddr(self._c_log))
        if host:
            L.rc_client_set_host(c, host.encode())
        self._c_clock = None
        if clock_ms is not None:  # tests: deterministic time for pings/retries
            self._c_clock = T.GET_TIME(lambda _c: int(clock_ms()))
            L.rc_client_set_get_time_millisecs_function(c, self._fnaddr(self._c_clock))
        self.set_user_agent(user_agent)

    @staticmethod
    def _fnaddr(cfunc) -> int:
        return C.cast(cfunc, C.c_void_p).value

    # ---------------- configuration ----------------
    @property
    def user_agent_clause(self) -> str:
        buf = C.create_string_buffer(64)
        self.lib.rc_client_get_user_agent_clause(self._client, buf, len(buf))
        return buf.value.decode()

    def set_user_agent(self, prefix: str) -> None:
        clause = self.user_agent_clause
        self.user_agent = prefix if clause in prefix else f"{prefix} {clause}"
        self._http.user_agent = self.user_agent

    def set_file_reader(self, reader: Optional[FileReader]) -> None:
        """Route rc_hash's file access through a Python FileReader (e.g. CsoFileReader()).
        None restores rcheevos' stdio reader."""
        T = self.T
        cbs = T.rc_hash_callbacks_t()
        self._file_reader = reader
        if reader is not None:
            self._c_fr = (T.FR_OPEN(reader._open), T.FR_SEEK(reader._seek), T.FR_TELL(reader._tell),
                          T.FR_READ(reader._read), T.FR_CLOSE(reader._close))
            fr = cbs.filereader
            fr.open, fr.seek, fr.tell, fr.read, fr.close = (self._fnaddr(f) for f in self._c_fr)
        self.lib.rc_client_set_hash_callbacks(self._client, C.byref(cbs))  # copied by rcheevos

    def set_host(self, host: Optional[str]) -> None:
        """e.g. 'http://127.0.0.1:8080'. None/'' -> https://retroachievements.org.
        (Never pass NULL to rc_client_set_host: 12.x strcpy's it.)"""
        self.lib.rc_client_set_host(self._client, host.encode() if host else b"")

    @property
    def hardcore(self) -> bool:
        return bool(self.lib.rc_client_get_hardcore_enabled(self._client))

    # ---------------- user ----------------
    def login_password(self, username: str, password: str, callback=None) -> None:
        key = self._remember(("login", callback, "password"))
        self.lib.rc_client_begin_login_with_password(self._client, username.encode(), password.encode(),
                                                     self._fnaddr(self._c_login_cb), key)

    def login_token(self, username: str, token: str, callback=None) -> None:
        key = self._remember(("login", callback, "token"))
        self.lib.rc_client_begin_login_with_token(self._client, username.encode(), token.encode(),
                                                  self._fnaddr(self._c_login_cb), key)

    def logout(self) -> None:
        self.lib.rc_client_logout(self._client)

    @property
    def user(self) -> Optional[dict]:
        p = self.lib.rc_client_get_user_info(self._client)
        if not p:
            return None
        u = p.contents
        d = dict(username=_s(u.username), display_name=_s(u.display_name), token=_s(u.token),
                 score=u.score, score_softcore=u.score_softcore, unread_messages=u.num_unread_messages,
                 avatar_url=_s(u.avatar_url))
        if hasattr(u, "avatar_last_updated"):
            d["avatar_last_updated"] = u.avatar_last_updated
        return d

    # ---------------- game ----------------
    def load_game(self, console_id: int, data=None, path: Optional[str] = None, callback=None) -> None:
        """Hash + identify + load.  Cartridges: pass data= (the unzipped ROM; rcheevos strips
        headers itself) and optionally path= (only its extension is used).  Discs, arcade
        zips, N64/NDS from disk: pass path=.  console_id 0 = guess from the extension."""
        ptr, size, keep = _buffer_pointer(data)
        self._load_console = console_id
        self._prepare_memory_for_load()
        key = self._remember(("load", callback, keep))  # rc_hash may reread the buffer (console_id 0)
        self.lib.rc_client_begin_identify_and_load_game(
            self._client, console_id, os.fsencode(path) if path else None, ptr, size,
            self._fnaddr(self._c_load_cb), key)

    def load_game_hash(self, game_hash: str, console_id: int = 0, callback=None) -> None:
        self._load_console = console_id
        self._prepare_memory_for_load()
        key = self._remember(("load", callback, None))
        self.lib.rc_client_begin_load_game(self._client, game_hash.encode(), self._fnaddr(self._c_load_cb), key)

    def change_media(self, path: Optional[str] = None, data=None, callback=None) -> None:
        """Disc swap (m3u / multi-disc).  Unrecognised discs disable achievements until a known one is inserted."""
        ptr, size, keep = _buffer_pointer(data)
        key = self._remember(("media", callback, keep))
        self.lib.rc_client_begin_identify_and_change_media(
            self._client, os.fsencode(path) if path else None, ptr, size, self._fnaddr(self._c_media_cb), key)

    @property
    def load_state(self) -> str:
        return LOAD_STATES.get(self.lib.rc_client_get_load_game_state(self._client), "?")

    @property
    def is_game_loaded(self) -> bool:
        return bool(self._client) and bool(self.lib.rc_client_is_game_loaded(self._client))

    @property
    def game(self) -> Optional[dict]:
        p = self.lib.rc_client_get_game_info(self._client)
        if not p:
            return None
        g = p.contents
        return dict(id=g.id, console_id=g.console_id, title=_s(g.title), hash=_s(g.hash),
                    badge_name=_s(g.badge_name), badge_url=_s(g.badge_url))

    def summary(self) -> dict:
        s = self.T.rc_client_user_game_summary_t()
        self.lib.rc_client_get_user_game_summary(self._client, C.byref(s))
        return {f: getattr(s, f) for f, _ in s._fields_}

    def _ach(self, a) -> dict:
        return dict(id=a.id, title=_s(a.title), description=_s(a.description), points=a.points,
                    badge_name=_sb(a.badge_name), badge_url=_s(a.badge_url), badge_locked_url=_s(a.badge_locked_url),
                    measured_progress=_sb(a.measured_progress), measured_percent=float(a.measured_percent),
                    state=ACHIEVEMENT_STATES.get(a.state, a.state), bucket=ACHIEVEMENT_BUCKETS.get(a.bucket, a.bucket),
                    unlocked=bool(a.unlocked & RC_CLIENT_ACHIEVEMENT_UNLOCKED_SOFTCORE),
                    unlocked_hardcore=bool(a.unlocked & RC_CLIENT_ACHIEVEMENT_UNLOCKED_HARDCORE),
                    unlock_time=int(a.unlock_time), type=ACHIEVEMENT_TYPES.get(a.type, a.type),
                    rarity=float(a.rarity), warning=a.id == RC_CLIENT_ACHIEVEMENT_WARNING_ID)

    def achievements(self, include_unofficial: bool = False) -> list[dict]:
        """Every achievement with lock state and measured progress ("3/10"), grouped by
        rcheevos' buckets (bucket_label holds the display heading)."""
        cat = RC_CLIENT_ACHIEVEMENT_CATEGORY_CORE | (RC_CLIENT_ACHIEVEMENT_CATEGORY_UNOFFICIAL if include_unofficial else 0)
        lst = self.lib.rc_client_create_achievement_list(self._client, cat, RC_CLIENT_ACHIEVEMENT_LIST_GROUPING_LOCK_STATE)
        out = []
        if not lst:
            return out
        try:
            L = lst.contents
            for b in range(L.num_buckets):
                bucket = L.buckets[b]
                for k in range(bucket.num_achievements):
                    d = self._ach(bucket.achievements[k].contents)
                    d["bucket_label"] = _s(bucket.label)
                    out.append(d)
        finally:
            self.lib.rc_client_destroy_achievement_list(lst)
        return out

    def achievement(self, achievement_id: int) -> Optional[dict]:
        p = self.lib.rc_client_get_achievement_info(self._client, achievement_id)
        return self._ach(p.contents) if p else None

    def rich_presence(self) -> str:
        buf = C.create_string_buffer(256)
        self.lib.rc_client_get_rich_presence_message(self._client, buf, len(buf))
        return buf.value.decode("utf-8", "replace")

    def unload_game(self, drain_timeout: float = 2.0) -> None:
        # let in-flight unlocks finish first (an unlock response with
        # AchievementsRemaining=0 that arrives after unload dereferences client->game)
        self.wait_until(lambda: not self.inflight["awardachievement"], drain_timeout)
        self.lib.rc_client_unload_game(self._client)
        self.memory.destroy()
        self._glue.mode = MEM_UNAVAILABLE
        self._mem_pending = False

    # ---------------- per frame ----------------
    def do_frame(self) -> None:
        """Call once after every retro_run()."""
        if self._closed:
            return
        self.pump()
        if self._mem_pending and not self._activate_memory():
            # core hasn't exposed its memory yet (e.g. maps arrive on the first retro_run):
            # don't evaluate achievements against zeros, just keep the queue moving
            self._mem_wait += 1
            if self._mem_wait < self.memory_wait_frames:
                self.lib.rc_client_idle(self._client)
                return
            log.warning("core exposes no memory for console %d; achievements will be unsupported", self._load_console)
            self._glue.mode = MEM_UNAVAILABLE
            self._mem_pending = False
        self.lib.rc_client_do_frame(self._client)

    def idle(self) -> None:
        """Call regularly (e.g. every frame of the pause menu) while not running frames."""
        if self._closed:
            return
        self.pump()
        self.lib.rc_client_idle(self._client)

    def can_pause(self) -> tuple[bool, int]:
        frames = C.c_uint32(0)
        ok = self.lib.rc_client_can_pause(self._client, C.byref(frames))
        return bool(ok), frames.value

    def reset(self) -> None:
        """After retro_reset(): resets achievement state; re-reads memory pointers
        (some cores reallocate on reset)."""
        self.lib.rc_client_reset(self._client)
        self.refresh_memory()

    # ---------------- save states ----------------
    def serialize_progress(self) -> Optional[bytes]:
        size = self.lib.rc_client_progress_size(self._client)
        if not size:
            return None
        buf = (C.c_uint8 * size)()
        if self.lib.rc_client_serialize_progress_sized(self._client, buf, size) != RC_OK:
            return None
        return bytes(buf)

    def deserialize_progress(self, data: Optional[bytes]) -> bool:
        """Call right after retro_unserialize().  data=None (state saved without
        achievement data) resets all achievement progress, as rcheevos recommends."""
        if data is None:
            return self.lib.rc_client_deserialize_progress_sized(self._client, None, 0) == RC_OK
        buf = (C.c_uint8 * len(data)).from_buffer_copy(data)
        return self.lib.rc_client_deserialize_progress_sized(self._client, buf, len(data)) == RC_OK

    # ---------------- memory plumbing ----------------
    def set_memory_map(self, descriptors: Optional[list]) -> None:
        """Copy of the core's RETRO_ENVIRONMENT_SET_MEMORY_MAPS descriptors (may be
        called again later, e.g. mGBA re-sends them on its first retro_run and on reset)."""
        self.memory.set_memory_map(descriptors)
        self.refresh_memory()

    def refresh_memory(self) -> None:
        """Rebuild the regions now if a game is active (maps changed, reset, core realloc)."""
        if self.is_game_loaded:
            self._init_memory_now()

    def _game_console(self) -> int:
        g = self.lib.rc_client_get_game_info(self._client)
        cid = g.contents.console_id if g else 0
        return cid or self._load_console

    def _prepare_memory_for_load(self) -> None:
        self.memory.destroy()
        self._glue.mode = MEM_DUMMY
        self._mem_pending = False
        self.lib.rc_client_set_read_memory_function(self._client, self._fnaddr(self._c_read_uninit))

    def _init_memory_now(self) -> bool:
        """rc_libretro_memory_init for the game's console.  LIVE if the core exposed real
        memory, else DUMMY (zeros) + pending: do_frame() keeps retrying before evaluating."""
        ok = self.memory.init(self._game_console())
        self._glue.mode = MEM_LIVE if ok else MEM_DUMMY
        self._mem_pending = not ok
        if not ok:
            self._mem_wait = 0
        addr = self._glue_read_addr if self._use_glue else self._fnaddr(self._c_read_py)
        self.lib.rc_client_set_read_memory_function(self._client, addr)
        return ok

    def _read_uninitialized(self, address, buf, num_bytes, client) -> int:
        # First read happens while rc_client validates addresses during game activation;
        # by then client->game (and its console id) is set.  Same approach as RetroArch.
        try:
            self._init_memory_now()
            return self._read_python(address, buf, num_bytes, client)
        except Exception:
            log.exception("memory init failed")
            return 0

    def _read_python(self, address, buf, num_bytes, client) -> int:
        mode = self._glue.mode
        if mode == MEM_LIVE:
            return self.lib.rc_libretro_memory_read(C.byref(self.memory.regions), address, buf, num_bytes)
        if mode == MEM_DUMMY:
            C.memset(buf, 0, num_bytes)
            return num_bytes
        return 0

    def _activate_memory(self) -> bool:
        wait = self._mem_wait
        ok = self._init_memory_now()
        self._mem_wait = wait  # keep counting frames while pending
        return ok

    # ---------------- HTTP / server_call ----------------
    def _server_call(self, request_p, callback, callback_data, client) -> None:
        try:
            req = request_p.contents  # only valid during this call - copy everything now
            job = _Job(req.url.decode(), req.post_data, _s(req.content_type), callback, callback_data)
            self.inflight[job.api] += 1
            self._http.submit(job)
        except Exception:
            log.exception("server_call failed")
            resp = self.T.rc_api_server_response_t(None, 0, RC_API_SERVER_RESPONSE_CLIENT_ERROR)
            self.T.SERVER_CALLBACK(callback)(C.byref(resp), callback_data)

    def pump(self) -> int:
        """Hand finished HTTP responses to rcheevos (on this thread). Returns how many."""
        n = 0
        while True:
            try:
                job, status, body = self._done.get_nowait()
            except queue.Empty:
                return n
            self.inflight[job.api] -= 1
            if self._closed:
                continue  # never call into rcheevos after rc_client_destroy
            self._deliver(job, status, body)
            n += 1

    def _deliver(self, job: _Job, status: int, body: bytes) -> None:
        if job.api == "awardachievement" and not self.is_game_loaded and b"AchievementsRemaining" in body:
            # rcheevos 12.x: rc_client_award_achievement_callback walks client->game->subsets
            # when AchievementsRemaining == 0, and client->game is NULL after unload -> segfault.
            try:
                data = json.loads(body)
                if data.get("AchievementsRemaining") == 0:
                    del data["AchievementsRemaining"]
                    body = json.dumps(data).encode()
            except ValueError:
                pass
        buf = C.create_string_buffer(body, len(body) + 1)  # NUL-terminated: rcheevos re-parses some bodies with strlen
        resp = self.T.rc_api_server_response_t(C.cast(buf, C.c_void_p), len(body), status)
        try:
            self.T.SERVER_CALLBACK(job.callback)(C.byref(resp), job.callback_data)
        finally:
            del buf
        if job.api != "login2" and (status == 401 or b'"invalid_credentials"' in body or b'"expired_token"' in body):
            self._emit("on_login_required", "server rejected the login token")

    def wait_until(self, predicate: Callable[[], bool], timeout: float = 10.0, interval: float = 0.005) -> bool:
        """Pump + idle until predicate() is true (startup, shutdown). Returns predicate()."""
        deadline = time.monotonic() + timeout
        while not predicate():
            if self._closed or time.monotonic() >= deadline:
                return predicate()
            self.idle()
            time.sleep(interval)
        return True

    # ---------------- callbacks from rcheevos ----------------
    def _remember(self, entry: tuple) -> int:
        key = self._next_key
        self._next_key += 1
        self._pending[key] = entry
        return key

    def _login_callback(self, result, message, client, userdata) -> None:
        try:
            _kind, cb, how = self._pending.pop(userdata or 0, ("login", None, "?"))
            msg = _s(message)
            if result == RC_OK:
                self._login_required_sent = False
            elif result in LOGIN_REQUIRED_RESULTS:
                self._emit("on_login_required", f"login with {how} failed: {msg}")
            self._emit("on_login", result, msg)
            if cb:
                cb(result, msg)
        except Exception:
            log.exception("login callback")

    def _load_callback(self, result, message, client, userdata) -> None:
        try:
            _kind, cb, _keep = self._pending.pop(userdata or 0, ("load", None, None))
            msg = _s(message)
            if result == RC_OK:
                if self._glue.mode != MEM_LIVE:  # never read yet (no memrefs) or core not ready
                    self._init_memory_now()
            elif result == RC_LOGIN_REQUIRED:
                self._emit("on_login_required", "game load needs a logged-in user")
            self._emit("on_game_loaded", result, msg)
            if cb:
                cb(result, msg)
        except Exception:
            log.exception("load callback")

    def _media_callback(self, result, message, client, userdata) -> None:
        try:
            entry = self._pending.pop(userdata or 0, ("media", None, None))
            if entry[1]:
                entry[1](result, _s(message))
        except Exception:
            log.exception("media callback")

    def _list_callback(self, result, message, lst, client, userdata) -> None:
        try:
            entry = self._pending.pop(userdata or 0, ("list", None, None))
            _kind, cb, destroy = entry
            # every rc_client_*_list_t starts with { entries*, uint32_t num_entries }
            count = C.cast(lst, C.POINTER(_ListHead)).contents.num_entries if lst else 0
            try:
                if cb:
                    cb(result, _s(message), lst, count)
            finally:
                if lst and destroy:
                    destroy(lst)
        except Exception:
            log.exception("list callback")

    def _log_message(self, message, client) -> None:
        rc_log.info("%s", _s(message))

    def _emit(self, name: str, *args) -> None:
        if name == "on_login_required":
            if self._login_required_sent:
                return
            self._login_required_sent = True
        hook = getattr(self, name, None)
        if hook is not None:
            try:
                hook(*args)
            except Exception:
                log.exception("%s handler raised", name)
        if self.on_event is not None:
            try:
                self.on_event(name, args)
            except Exception:
                log.exception("on_event handler raised")

    def _event_handler(self, event_p, client) -> None:
        try:
            ev = event_p.contents  # pointers inside are only valid during this call
            t = ev.type
            if t == EV_ACHIEVEMENT_TRIGGERED:
                self._emit("on_achievement_triggered", self._ach(ev.achievement.contents))
            elif t in (EV_PROGRESS_SHOW, EV_PROGRESS_UPDATE):
                self._emit("on_progress", self._ach(ev.achievement.contents))
            elif t == EV_PROGRESS_HIDE:
                self._emit("on_progress", None)
            elif t in (EV_CHALLENGE_SHOW, EV_CHALLENGE_HIDE):
                self._emit("on_challenge", self._ach(ev.achievement.contents), t == EV_CHALLENGE_SHOW)
            elif t == EV_GAME_COMPLETED:
                g = self.game or {}
                self._emit("on_game_completed", dict(game_id=g.get("id"), title=g.get("title"), mastered=self.hardcore))
            elif t == EV_SUBSET_COMPLETED:
                s = ev.subset.contents
                self._emit("on_subset_completed", dict(id=s.id, title=_s(s.title), badge_url=_s(s.badge_url)))
            elif t == EV_SERVER_ERROR:
                e = ev.server_error.contents
                err = dict(api=_s(e.api), message=_s(e.error_message), result=e.result, related_id=e.related_id)
                self._emit("on_server_error", err)
                if e.result in LOGIN_REQUIRED_RESULTS:
                    self._emit("on_login_required", f"{err['api']}: {err['message']}")
            elif t == EV_DISCONNECTED:
                self.disconnected = True
                self._emit("on_disconnected")
            elif t == EV_RECONNECTED:
                self.disconnected = False
                self._emit("on_reconnected")
            elif t == EV_RESET:
                self._emit("on_reset_requested")
            elif t in (EV_LEADERBOARD_STARTED, EV_LEADERBOARD_FAILED, EV_LEADERBOARD_SUBMITTED):
                lb = ev.leaderboard.contents
                kind = {2: "started", 3: "failed", 4: "submitted"}[t]
                self._emit("on_leaderboard", kind, dict(id=lb.id, title=_s(lb.title), value=_s(lb.tracker_value)))
            elif t in (EV_TRACKER_SHOW, EV_TRACKER_HIDE, EV_TRACKER_UPDATE):
                tr = ev.leaderboard_tracker.contents
                kind = {10: "tracker_show", 11: "tracker_hide", 12: "tracker_update"}[t]
                self._emit("on_leaderboard", kind, dict(id=tr.id, display=_sb(tr.display)))
            elif t == EV_LEADERBOARD_SCOREBOARD:
                sb = ev.leaderboard_scoreboard.contents
                self._emit("on_leaderboard", "scoreboard", dict(id=sb.leaderboard_id, rank=sb.new_rank,
                                                                 entries=sb.num_entries, score=_sb(sb.submitted_score)))
        except Exception:
            log.exception("event handler")

    # ---------------- list fetches (thin; used by tests) ----------------
    def fetch_list(self, kind: str, arg: int, callback) -> None:
        """kind: hash_library(console) | game_titles(game_id) | all_progress(console) |
        leaderboard(leaderboard_id) | game_list(console).  callback(result, msg, list_ptr, count)."""
        L, c, f = self.lib, self._client, self._fnaddr(self._c_list_cb)
        destroy = {"hash_library": L.rc_client_destroy_hash_library, "game_titles": L.rc_client_destroy_game_title_list,
                   "all_progress": L.rc_client_destroy_all_user_progress,
                   "leaderboard": L.rc_client_destroy_leaderboard_entry_list,
                   "game_list": getattr(L, "rc_client_destroy_game_list", None)}[kind]
        key = self._remember(("list", callback, destroy))
        if kind == "hash_library":
            L.rc_client_begin_fetch_hash_library(c, arg, f, key)
        elif kind == "game_titles":
            ids = (C.c_uint32 * 1)(arg)
            L.rc_client_begin_fetch_game_titles(c, ids, 1, f, key)
        elif kind == "all_progress":
            L.rc_client_begin_fetch_all_user_progress(c, arg, f, key)
        elif kind == "leaderboard":
            L.rc_client_begin_fetch_leaderboard_entries(c, arg, 1, 10, f, key)
        elif kind == "game_list":
            L.rc_client_begin_fetch_game_list(c, arg, f, key)

    # ---------------- teardown ----------------
    def close(self, drain_timeout: float = 2.0) -> None:
        """Give in-flight requests (unlocks!) a moment, then destroy the client.
        Responses that arrive later are dropped, never passed to the freed client."""
        if self._closed:
            return
        self.wait_until(lambda: sum(v for v in self.inflight.values() if v > 0) == 0, drain_timeout)
        self._closed = True
        self.lib.rc_client_destroy(self._client)
        self._client = None
        self._http.stop()
        self.memory.destroy()

    destroy = close

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def pending_requests(self) -> int:
        return sum(v for v in self.inflight.values() if v > 0)


if __name__ == "__main__":  # self-check on a Pi: python3 -m pitato.rcheevos [path/to/librcheevos.so]
    import sys
    _lib = RCheevos(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"{_lib.path}: rcheevos {_lib.version_string}, "
          f"{'layouts verified against ' + str(len(_lib.abi)) + ' C entries' if _lib.abi else 'NO ABI table'}, "
          f"time_t={_lib.abi.get('sizeof:time_t', '?')} bytes, C memory reader={'yes' if _lib.has_glue else 'no'}")
    _c = RAClient(_lib, user_agent=make_user_agent("SelfCheck", "0.0.1"), host="http://127.0.0.1:9")
    print("User-Agent:", _c.user_agent)
    _c.close(drain_timeout=0)
