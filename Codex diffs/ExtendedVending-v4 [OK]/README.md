# ExtendedVending-v4 [OK]

## Contents
- Patch: `ExtendedVending-v4 [OK].patch`
- Accessories:
  - `accessories/Changelog.txt`
  - `accessories/LEIAME.txt`
  - `accessories/README.txt`
  - `accessories/fe4234cd39e341985b1006a371acf9119a3ae248.diff`
  - `accessories/main.sql`

## Runtime YAML format
Use `db/import/item_db_extended_vending.yml` with:

```yml
Header:
  Type: ITEM_VENDING_DB
  Version: 1

Body:
  - Item: Zeny
    DisplayItem: 1750
    DisplayName: "Zeny"
    StorePrefix: "[Z]"

  # - Item: Hydra_Card
  #   DisplayAegisName: Hydra_Card
  #   DisplayName: "Hydra"
  #   StorePrefix: "[HYDRA]"

# Item/AegisName entries are matched case-insensitively.
# DisplayItem/DisplayAegisName controls icon/name shown by the selection window.
```
