# Custom Drops Mapflag - Implementation Notes

## Goal
Create a mapflag system (`mobdrop`) that supports both legacy script mapflag lines and production-grade YAML rules.

## YAML Rule Capabilities
- Map-scoped rules.
- Optional monster filter:
  - single monster (`Monster`)
  - multiple monsters (`Monsters` list)
  - omitted = all monsters.
- Item source:
  - exact item (`Item`), or
  - random group source (`ItemGroup`, subgroup 1 list-only selection).
- Dynamic drop chance range (`Rate.Min` to `Rate.Max`).
- Bind mode selection (`Free`, `Account`, `Character` aliases supported).
- Optional random option group (`RandomOptionGroup`).

## Runtime Reload
- Added `@reloadmapdb` atcommand.
- Reload target: `mapflag_mobdrop.yml` + imported override YAML.

## Validation Rules
- Unknown map/item/mob rejected.
- Unknown random option group rejected.
- Unknown item group rejected.
- `Rate.Max >= Rate.Min` required.
- Exactly one of `Item` or `ItemGroup` must be set.
- ItemGroup internal entry drop percentages are ignored by MF_MOBDROP.

## Compatibility Notes
- Keeps legacy `mapflag mobdrop` parser behavior.
- YAML and legacy rules are additive.
- No SQL migration required.
