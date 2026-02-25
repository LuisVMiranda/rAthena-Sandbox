# Custom drops mapflag

This package adds a **new mapflag** (`mobdrop`) for rAthena so administrators can configure map-specific extra monster drops.

## Folder structure

- `actual .DIFF/Custom drops mapflag.DIFF`
  - Main patch file with source-level changes.
- `required files/npc/custom/mapflag/custom_drops_mapflag.txt`
  - Example mapflag lines to load after applying the patch.
- `assets/IMPLEMENTATION_NOTES.md`
  - Design behavior, checks, and compatibility notes.

## Feature summary

After applying the diff:

- New mapflag: `mobdrop`
- Syntax:
  - `<mapname> mapflag mobdrop <item_id>,<rate>{,<mob_id>}`
- Behavior:
  - Adds additional independent drop rolls per monster death.
  - Optional `mob_id` scopes the rule to a specific monster.
  - `off` clears all `mobdrop` rules from that map.

## Example

```txt
prontera	mapflag	mobdrop	512,500
prontera	mapflag	mobdrop	909,100,1002
```

## Important notes / risks

1. **Rate stacking**
   - Multiple `mobdrop` lines stack and each line rolls independently.
   - If admins configure too many high-rate entries, economy inflation risk increases.

2. **Per-map rule cap**
   - The patch enforces `MAX_MOBDROP_RULES_PER_MAP` (default 128).
   - Further lines are skipped with warning logs.

3. **Scope with existing systems**
   - This patch is additive and designed to coexist with existing default mob drops and `map_drop_db` drops.

## Recommended rollout checklist

1. Apply patch to a staging emulator clone.
2. Rebuild map-server.
3. Add test rules to a non-critical map.
4. Kill targeted and non-targeted monsters to confirm rule filtering.
5. Monitor drop logs and economy metrics before production rollout.
