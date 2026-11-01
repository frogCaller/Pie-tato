/*
 * rcheevos_glue.c: a little C built into librcheevos.so beside rcheevos (setup.sh), for pitato/rcheevos.py.
 *
 * 1. ra_abi_table(): sizeof/offsetof of every struct rcheevos.py reads, as compiled by this cc with these
 *    headers. rcheevos.py checks its ctypes layouts against it as it loads, so a mismatch (another rcheevos, or a
 *    4-byte time_t on a 32-bit Pi) stops it with an error instead of reading the wrong memory.
 *
 * 2. ra_read_memory(): rcheevos's memory reads (one per memory reference, each frame) from the game's memory as
 *    rc_libretro maps it, without going through Python: it matters on a Pi Zero. rcheevos.py keeps a ra_memory_t
 *    in the client's userdata, and turns it on once the emulator's memory is there.
 *
 * Nothing here changes what rcheevos does.
 */

#include "rc_client.h"
#include "rc_consoles.h"
#include "rc_hash.h"
#include "rc_libretro.h"
#include "rc_version.h"

#include <stddef.h>
#include <string.h>
#include <time.h>

#if defined(__GNUC__) && __GNUC__ >= 4
 #define RA_GLUE_API __attribute__((visibility("default")))
#else
 #define RA_GLUE_API
#endif

/* ===== memory read glue ===== */

enum {
  RA_MEMORY_UNAVAILABLE = 0, /* every read fails (achievements get disabled) */
  RA_MEMORY_DUMMY = 1,       /* pretend memory exists (zeros) - used while the core hasn't exposed it yet */
  RA_MEMORY_LIVE = 2         /* serve reads from regions */
};

typedef struct ra_memory_t {
  rc_libretro_memory_regions_t* regions;
  uint32_t mode;
} ra_memory_t;

RA_GLUE_API uint32_t RC_CCONV ra_read_memory(uint32_t address, uint8_t* buffer, uint32_t num_bytes, rc_client_t* client)
{
  const ra_memory_t* mem = (const ra_memory_t*)rc_client_get_userdata(client);
  if (!mem)
    return 0;

  switch (mem->mode) {
    case RA_MEMORY_LIVE:
      return mem->regions ? rc_libretro_memory_read(mem->regions, address, buffer, num_bytes) : 0;

    case RA_MEMORY_DUMMY:
      memset(buffer, 0, num_bytes);
      return num_bytes;

    default:
      return 0;
  }
}

/* ===== ABI table ===== */

typedef struct ra_abi_entry_t {
  const char* name;
  size_t value;
} ra_abi_entry_t;

#define S(type) { "sizeof:" #type, sizeof(type) }
#define O(type, field) { #type "." #field, offsetof(type, field) }

static const ra_abi_entry_t ra_abi_entries[] = {
  { "rcheevos_version", RCHEEVOS_VERSION },
  S(time_t), S(size_t), S(void*), S(int), S(long),

  S(rc_api_request_t),
  O(rc_api_request_t, url), O(rc_api_request_t, post_data), O(rc_api_request_t, content_type), O(rc_api_request_t, buffer),

  S(rc_api_server_response_t),
  O(rc_api_server_response_t, body), O(rc_api_server_response_t, body_length), O(rc_api_server_response_t, http_status_code),

  S(rc_client_user_t),
  O(rc_client_user_t, display_name), O(rc_client_user_t, username), O(rc_client_user_t, token),
  O(rc_client_user_t, score), O(rc_client_user_t, score_softcore), O(rc_client_user_t, num_unread_messages),
  O(rc_client_user_t, avatar_url),
#if RCHEEVOS_VERSION >= RCHEEVOS_MAKE_VERSION(12, 4, 0)
  O(rc_client_user_t, avatar_last_updated),
#endif

  S(rc_client_user_game_summary_t),
  O(rc_client_user_game_summary_t, num_core_achievements), O(rc_client_user_game_summary_t, num_unofficial_achievements),
  O(rc_client_user_game_summary_t, num_unlocked_achievements), O(rc_client_user_game_summary_t, num_unsupported_achievements),
  O(rc_client_user_game_summary_t, points_core), O(rc_client_user_game_summary_t, points_unlocked),
  O(rc_client_user_game_summary_t, beaten_time), O(rc_client_user_game_summary_t, completed_time),

  S(rc_client_game_t),
  O(rc_client_game_t, id), O(rc_client_game_t, console_id), O(rc_client_game_t, title), O(rc_client_game_t, hash),
  O(rc_client_game_t, badge_name), O(rc_client_game_t, badge_url),

  S(rc_client_subset_t),
  O(rc_client_subset_t, id), O(rc_client_subset_t, title), O(rc_client_subset_t, badge_name),
  O(rc_client_subset_t, num_achievements), O(rc_client_subset_t, num_leaderboards), O(rc_client_subset_t, badge_url),

  S(rc_client_achievement_t),
  O(rc_client_achievement_t, title), O(rc_client_achievement_t, description), O(rc_client_achievement_t, badge_name),
  O(rc_client_achievement_t, measured_progress), O(rc_client_achievement_t, measured_percent), O(rc_client_achievement_t, id),
  O(rc_client_achievement_t, points), O(rc_client_achievement_t, unlock_time), O(rc_client_achievement_t, state),
  O(rc_client_achievement_t, category), O(rc_client_achievement_t, bucket), O(rc_client_achievement_t, unlocked),
  O(rc_client_achievement_t, rarity), O(rc_client_achievement_t, rarity_hardcore), O(rc_client_achievement_t, type),
  O(rc_client_achievement_t, badge_url), O(rc_client_achievement_t, badge_locked_url),

  S(rc_client_achievement_bucket_t),
  O(rc_client_achievement_bucket_t, achievements), O(rc_client_achievement_bucket_t, num_achievements),
  O(rc_client_achievement_bucket_t, label), O(rc_client_achievement_bucket_t, subset_id), O(rc_client_achievement_bucket_t, bucket_type),

  S(rc_client_achievement_list_t),
  O(rc_client_achievement_list_t, buckets), O(rc_client_achievement_list_t, num_buckets),

  S(rc_client_leaderboard_t),
  O(rc_client_leaderboard_t, title), O(rc_client_leaderboard_t, description), O(rc_client_leaderboard_t, tracker_value),
  O(rc_client_leaderboard_t, id), O(rc_client_leaderboard_t, state), O(rc_client_leaderboard_t, format),
  O(rc_client_leaderboard_t, lower_is_better),

  S(rc_client_leaderboard_tracker_t),
  O(rc_client_leaderboard_tracker_t, display), O(rc_client_leaderboard_tracker_t, id),

  S(rc_client_leaderboard_scoreboard_entry_t),
  O(rc_client_leaderboard_scoreboard_entry_t, username), O(rc_client_leaderboard_scoreboard_entry_t, rank),
  O(rc_client_leaderboard_scoreboard_entry_t, score),

  S(rc_client_leaderboard_scoreboard_t),
  O(rc_client_leaderboard_scoreboard_t, leaderboard_id), O(rc_client_leaderboard_scoreboard_t, submitted_score),
  O(rc_client_leaderboard_scoreboard_t, best_score), O(rc_client_leaderboard_scoreboard_t, new_rank),
  O(rc_client_leaderboard_scoreboard_t, num_entries), O(rc_client_leaderboard_scoreboard_t, top_entries),
  O(rc_client_leaderboard_scoreboard_t, num_top_entries),

  S(rc_client_server_error_t),
  O(rc_client_server_error_t, error_message), O(rc_client_server_error_t, api), O(rc_client_server_error_t, result),
  O(rc_client_server_error_t, related_id),

  S(rc_client_event_t),
  O(rc_client_event_t, type), O(rc_client_event_t, achievement), O(rc_client_event_t, leaderboard),
  O(rc_client_event_t, leaderboard_tracker), O(rc_client_event_t, leaderboard_scoreboard),
  O(rc_client_event_t, server_error), O(rc_client_event_t, subset),

  S(rc_memory_region_t),
  O(rc_memory_region_t, start_address), O(rc_memory_region_t, end_address), O(rc_memory_region_t, real_address),
  O(rc_memory_region_t, type), O(rc_memory_region_t, description),
  S(rc_memory_regions_t),
  O(rc_memory_regions_t, region), O(rc_memory_regions_t, num_regions),

  S(rc_libretro_memory_regions_t),
  O(rc_libretro_memory_regions_t, data), O(rc_libretro_memory_regions_t, size),
  O(rc_libretro_memory_regions_t, total_size), O(rc_libretro_memory_regions_t, count),
  S(rc_libretro_core_memory_info_t),
  O(rc_libretro_core_memory_info_t, data), O(rc_libretro_core_memory_info_t, size),

  S(struct retro_memory_descriptor),
  O(struct retro_memory_descriptor, flags), O(struct retro_memory_descriptor, ptr), O(struct retro_memory_descriptor, offset),
  O(struct retro_memory_descriptor, start), O(struct retro_memory_descriptor, select), O(struct retro_memory_descriptor, disconnect),
  O(struct retro_memory_descriptor, len), O(struct retro_memory_descriptor, addrspace),
  S(struct retro_memory_map),
  O(struct retro_memory_map, descriptors), O(struct retro_memory_map, num_descriptors),

  S(ra_memory_t),
  O(ra_memory_t, regions), O(ra_memory_t, mode),

  { NULL, 0 }
};

RA_GLUE_API const ra_abi_entry_t* ra_abi_table(void)
{
  return ra_abi_entries;
}
