# MF_BLOOD_TAX [OK]

Adds mapflag `blood_tax` (`mf_blood_tax`) to tax skill usage by HP.

## Behavior
- On maps with `mapflag blood_tax`, each skill cast consumes **feature.blood_tax_hp_rate% of Max HP** (default: 2%).
- If current HP is below the tax, cast is blocked with:
  - `Você não tem sangue suficiente para este sacrifício.`
- Filter rules:
  - Passive skills are ignored.
  - Skills that already consume HP by default are ignored.

## Files
- `actual .DIFF/MF_BLOOD_TAX [OK].DIFF`
- `required files/conf/mapflag/blood_tax.conf`
- `conf/battle/feature.conf`
