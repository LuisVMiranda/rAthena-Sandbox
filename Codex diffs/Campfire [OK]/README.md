# Campfire

Reusable diff package for an item-driven temporary campfire system.

## What this system does
- Consumes **Matchstick** (`item_id: 7035`) on use.
- Spawns a temporary **bonfire NPC sprite** (`class: 10252`) near the player.
- Duration, pulse interval, regen rates, range, cooldown and icon are now configurable via `battle_config` entries (`feature.campfire_*`).
- Disabled automatically on **GvG** and **Battleground** maps.
- Supports mapflag **`nocampfire`** (constant `MF_NOCAMPFIRE`) to block Matchstick usage per-map.
- Campfire logic updates every 1000ms for zone/visual sync, while healing cadence follows `feature.campfire_tick_interval`.
- Every active heal pulse, campfire heals owner and party members in range with visible recovery numbers.
- Status icon is applied when entering the zone and removed when leaving/expiring (no countdown timer behavior).
- NPC-top progress bar is sent from source packet handling (`clif_progressbar_npc_area`) without locking player movement.
- Ground visuals use non-skill visual effects (`feature.campfire_ground_effect`) on campfire cells in a cross footprint.
- Campfire auto-removes when time expires.

## Files in this package
- `actual .DIFF/Campfire.DIFF` - source patch to apply.
- `required files/npc/custom/campfire_system.txt` - runtime duplication template NPC.
- `required files/npc/scripts_custom.conf.snippet.txt` - line to enable script loading.
- `required files/conf/battle/feature.conf.snippet.txt` - configurable Campfire battle_config keys.
- `required files/conf/msg_conf/map_msg.conf.snippet.txt` - Campfire localized message ids.
- `assets/IMPLEMENTATION_NOTES.md` - behavior, constraints, and extension notes.

## Integration checklist
1. Apply `actual .DIFF/Campfire.DIFF`.
2. Copy `required files/npc/custom/campfire_system.txt` to `npc/custom/campfire_system.txt`.
3. Add snippet line to your active scripts conf (commonly `npc/scripts_custom.conf`).
4. Append `required files/conf/msg_conf/map_msg.conf.snippet.txt` into `conf/msg_conf/map_msg.conf`.
5. Reload/restart map-server.

## Scope and safety
- The logic is isolated to item `7035` handling and NPC runtime duplication flow.
- Does not modify drop, battle formula, status formula, or mob AI systems.

## About OnCampfireStart / OnCampfireStartVIP
- In the current implementation these labels are not used by source logic anymore; campfire timing/visuals are source-driven.
- You can still define those labels for custom script-side hooks if you later call them manually from source or scripts.
- Default behavior does not require them.

## Optional per-player language
- Set `feature.campfire_language` in battle config:
  - `1` = English (default)
  - `2` = Portuguese
  - `3` = Spanish
- Optional per-character override: `CAMPFIRE_LANG` (same values).


## Optional mapflag
```txt
prontera	mapflag	nocampfire
```


## Message source
- Campfire UI strings are generated in source by `npc_campfire_localized()` in `src/map/npc.cpp` and honor `feature.campfire_language` (optional `CAMPFIRE_LANG` override).

## Updates
- Includes bCampfireHeal, fixed/percent heal mode, and latest party HP + campfire tick/name fixes.
