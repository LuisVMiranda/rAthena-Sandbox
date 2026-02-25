# No Mercy mapflag

Adds `mapflag no_mercy` that reduces HP/SP recovery from skill heals and consumable recovery.

## Behavior
- On maps with `no_mercy`, recovery is multiplied by `feature.no_mercy_recover_rate / 100`.
- Default `feature.no_mercy_recover_rate: 20` means keep only 20% (80% reduction).

## Files
- `actual .DIFF/No Mercy mapflag.DIFF`
- `required files/conf/mapflag/no_mercy.conf` (operator reference)
