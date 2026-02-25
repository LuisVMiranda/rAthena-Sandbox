# Custom Drops Mapflag - Implementation Notes

## Goal
Create a new mapflag (`mobdrop`) that allows map-specific extra drops from monster deaths.

## Behavior
- Mapflag can be declared multiple times per map.
- Each declaration appends a new drop rule.
- Rule can be global (all monsters) or scoped to a single monster ID.
- Rules are rolled independently at death time.

## Intended Parsing Rule
`<mapname> mapflag mobdrop <item_id>,<rate>{,<mob_id>}`

## Limits
- Maximum 128 rules per map (adjustable in patch with `MAX_MOBDROP_RULES_PER_MAP`).
- Rate is capped to `1..10000`.

## Security / Integrity Checks
- Reject invalid item IDs.
- Reject invalid mob IDs when provided.
- Reject malformed input lines.
- Prevent adding rules beyond configured per-map limit.

## Compatibility Notes
- Designed to be self-contained and not alter existing `map_drop_db.yml` behavior.
- Does not require SQL migration.
