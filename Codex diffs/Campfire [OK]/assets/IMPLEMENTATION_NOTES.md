# Implementation notes

## Runtime model
- `pc_useitem()` checks `feature.campfire_trigger_item_id` and calls `npc_campfire_use_item()`.
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
- Trigger item is configurable via `feature.campfire_trigger_item_id` (default `7035`).

## Configurability (battle_config)
- `feature.campfire_nonvip_duration` (seconds)
- `feature.campfire_vip_duration` (seconds)
- `feature.campfire_tick_interval` (seconds, default 5)
- `feature.campfire_range` (cells, default 8)
- `feature.campfire_hp_percent`
- `feature.campfire_sp_percent`
- `feature.campfire_heal_mode` (`0`=percent, `1`=fixed, legacy fallback)
- `feature.campfire_hp_heal_mode` (`-1`=legacy fallback, `0`=percent, `1`=fixed)
- `feature.campfire_sp_heal_mode` (`-1`=legacy fallback, `0`=percent, `1`=fixed)
- `feature.campfire_hp_fixed` (default 150)
- `feature.campfire_sp_fixed` (default 5)
- `feature.campfire_trigger_item_id`
- `feature.campfire_cooldown` (seconds)
- `feature.campfire_icon` (status icon id, `0` disables icon)

## Abuse prevention
- Campfire use is blocked on GvG and Battleground maps.
- Campfire use is also blocked when mapflag `nocampfire` is set.
- Owner-level cooldown is enforced after use.

## UI and progress
- Icon is shown to healed targets while pulse effect is active.
- Campfire enter notification is shown via `showscript` above the character, including owner name and remaining lifetime.
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
- Source checks battle config `feature.campfire_language` (`1` EN, `2` PT, `3` ES; default 2/PT).
- Optional per-character override via global variable `CAMPFIRE_LANG`.
- Applied to zone enter/leave and final countdown text.

## OnCampfireStart labels
- `OnCampfireStart` and `OnCampfireStartVIP` are currently informational only in script template; the source implementation no longer depends on them to avoid blocking behavior.


## Message source
- Runtime texts are loaded via `msg_txt()` ids in `conf/msg_conf/map_msg.conf` (ids `1541..1549`).
- Helper function: `npc_campfire_localized()` in `src/map/npc.cpp`.
- Keep campfire message IDs **below `MAP_MAX_MSG`** (default map-server cap is `2500` in `src/map/map.cpp`). If higher IDs are needed, raise `MAP_MAX_MSG` via `src/custom/defines_pre.hpp` and rebuild.


## Campfire heal bonus
- New script bonus `bCampfireHeal,<percent>;` modifies campfire healing (positive amplifies, negative reduces).
- Works from item scripts and random options because it is implemented as a normal `bonus` parameter.

- Ensure `npc/custom/campfire_system.txt` is present and enabled in `npc/scripts_custom.conf`; otherwise no campfire can be spawned from item 7035.

- Healing mode can be configured per stat; `-1` falls back to legacy `feature.campfire_heal_mode`.
