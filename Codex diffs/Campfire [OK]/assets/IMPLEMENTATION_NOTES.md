# Implementation notes

## Runtime model
- `pc_useitem()` intercepts `nameid == 7035` and calls `npc_campfire_use_item()`.
- A hidden template NPC (`CAMPFIRE_TEMPLATE`) is duplicated at runtime with visual class `10252`.
- Active campfires are tracked by NPC ID and owner char ID.
- Two timers are used:
  - pulse timer every 10s for regeneration
  - expiration timer at 60s / 120s based on VIP

## Regeneration target rules
- Campfire heals:
  - owner always
  - same-party players (`party_id` match)
  - only players currently in 9-cell radius around the campfire NPC

## Cleanup safety
- On expiry, NPC is unloaded and internal tracking is erased.
- If NPC is unloaded by any other path, tracking/timers are cleaned in `npc_unload()`.
- Prevents duplicate active campfires per owner.

## Potential operational risks
- If `npc/custom/campfire_system.txt` is not loaded, item use fails safely and logs a warning.
- Hardcoded values (range, interval, heal percent) may need balancing per server.
- Uses direct item ID hook (`7035`), so custom item remaps should be adjusted in source.

## Configurability (battle_config)
- `feature.campfire_nonvip_duration` (seconds)
- `feature.campfire_vip_duration` (seconds)
- `feature.campfire_tick_interval` (seconds)
- `feature.campfire_range` (cells)
- `feature.campfire_hp_percent`
- `feature.campfire_sp_percent`
- `feature.campfire_cooldown` (seconds)
- `feature.campfire_icon` (status icon id, `0` disables icon)

## Abuse prevention
- Campfire use is blocked on GvG and Battleground maps.
- Campfire use is also blocked when mapflag `nocampfire` is set.
- Owner-level cooldown is enforced after use.

## UI and progress
- Icon is shown to healed targets while pulse effect is active.
- Campfire countdown (final 5 seconds) is shown through `showscript` from source timers to avoid movement lock from progressbar-style blocking.

## Tick/Heal split model
- Runtime tick loop is fixed at **1000ms** for smooth zone enter/leave checks, icon state, and countdown/effect updates.
- Actual HP/SP healing cadence remains controlled by `feature.campfire_tick_interval`.

## Progress bar behavior
- Instead of script-sleep `progressbar_npc`, the system updates NPC progressbar packets directly each tick (`nd->progressbar.*` + `clif_progressbar_npc_area`).
- This keeps players fully movable while still showing progress over the campfire NPC.

## Ground effects
- Every 1000ms tick, non-skill effect ids are emitted to players standing on campfire cells in a cross footprint (center + N/S/E/W arms) using integer half-range derived from `feature.campfire_range`.
- Effect id is configurable via `feature.campfire_ground_effect`.

## Localization
- Source checks battle config `feature.campfire_language` (`1` EN, `2` PT, `3` ES).
- Optional per-character override via global variable `CAMPFIRE_LANG`.
- Applied to zone enter/leave and final countdown text.

## OnCampfireStart labels
- `OnCampfireStart` and `OnCampfireStartVIP` are currently informational only in script template; the source implementation no longer depends on them to avoid blocking behavior.


## Message source
- Runtime texts are loaded via `msg_txt()` ids in `conf/msg_conf/map_msg.conf` (ids `2901..2926`).
- Helper function: `npc_campfire_localized()` in `src/map/npc.cpp`.


## Campfire heal bonus
- New script bonus `bCampfireHeal,<percent>;` modifies campfire healing (positive amplifies, negative reduces).
- Works from item scripts and random options because it is implemented as a normal `bonus` parameter.
