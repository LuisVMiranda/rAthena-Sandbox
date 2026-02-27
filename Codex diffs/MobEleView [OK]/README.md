# MobEleView [OK]

This folder packages the MobEleView implementation for reuse in other projects.

## Included files
- `MobEleView [OK].patch`: Patch payload for the integrated implementation.
- `accessories/original-reference.patch`: Snapshot of the original reference diff used during adaptation.

## Notes
- Current implementation uses `mob_ele_view` battle config toggle.
- Element title/group is injected in `clif_name()` for clients that support title/group metadata.
- MobEleView now keeps title/group values synced in unit data to prevent loss after subsequent mob updates.
- A persistent second line (`unit_data.secondary_name`) is used so line 2 never falls back to base mob name during resend paths.
- MobEleView resend path is prioritized over `show_mob_info` for supported title/group clients to avoid `ZC_ACK_REQNAMEALL` reverting line 2 to base mob name during movement refreshes.

- For supported clients, `PACKET_ZC_ACK_REQNAMEALL_NPC` renders `title` on line 1 and `name` on line 2; this package places `Monster (HP%)` in `title` and `Race [S|M|L]` in `name` (short size tags in brackets).
