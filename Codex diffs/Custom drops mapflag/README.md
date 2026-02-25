# Custom drops mapflag

This package adds a **new mapflag** (`mobdrop`) for rAthena and now supports a **full YAML-driven rule database**.

## Folder structure

- `actual .DIFF/Custom drops mapflag.DIFF`
  - Main patch file with source-level changes.
- `required files/npc/custom/mapflag/custom_drops_mapflag.txt`
  - Legacy script mapflag sample syntax (still supported).
- `required files/db/mapflag_mobdrop.yml`
  - YAML boilerplate with complete syntax and accepted values.
- `required files/db/import/mapflag_mobdrop.yml`
  - Production override template.
- `assets/IMPLEMENTATION_NOTES.md`
  - Design behavior, checks, and compatibility notes.

## Feature summary

After applying the diff:

- New mapflag: `mobdrop`
- Two configuration modes:
  1. Legacy script mapflag line: `<mapname> mapflag mobdrop <item_id>,<rate>{,<mob_id>}`
  2. YAML database (`db/mapflag_mobdrop.yml`) with:
     - map
     - single monster OR monster list
     - dynamic rate (`Min`/`Max`)
     - bind mode (free/account/char)
     - optional random option group
     - optional `ItemGroup` source for random item pool drops

## Runtime reload

- New source-level atcommand: `@reloadmapdb`
- Purpose: reload `mapflag_mobdrop.yml` and imported override file during runtime.

## Important notes / risks

1. **Rate stacking**
   - Multiple rules can stack and each rule rolls independently.
   - If admins configure too many high-rate entries, economy inflation risk increases.

2. **Configuration source overlap**
   - Legacy script mapflag rules and YAML rules are additive.
   - During migration, avoid duplicating the same rule in both systems.

3. **ItemGroup behavior**
   - `ItemGroup` selects one random item from subgroup 1 per successful rule roll.
   - Item-group internal drop-rate percentages are intentionally ignored for this system.
   - Final chance is fully controlled by `Rate.Min`/`Rate.Max` in `mapflag_mobdrop.yml`.
   - Ensure referenced group exists in `item_group_db.yml`.

## Recommended rollout checklist

1. Apply patch to a staging emulator clone.
2. Rebuild map-server.
3. Define rules in `db/import/mapflag_mobdrop.yml`.
4. Use `@reloadmapdb` to load changes.
5. Test all requested variants:
   - single monster
   - monster list
   - item direct
   - item group
   - all bind modes
6. Monitor drop logs and economy metrics before production rollout.
