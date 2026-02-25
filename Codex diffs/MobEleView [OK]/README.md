# MobEleView [OK]

This folder packages the MobEleView implementation for reuse in other projects.

## Included files
- `MobEleView [OK].patch`: Patch payload for the integrated implementation.
- `accessories/original-reference.patch`: Snapshot of the original reference diff used during adaptation.

## Notes
- Current implementation uses `mob_ele_view` battle config toggle.
- Element title/group is injected in `clif_name()` for clients that support title/group metadata.

- For supported clients, `PACKET_ZC_ACK_REQNAMEALL_NPC` renders `title` on line 1 and `name` on line 2; this package places `Monster (HP%)` in `title` and `Race Size` in `name`.
