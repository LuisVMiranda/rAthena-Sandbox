# MF_GEAR_LOCK [OK]

Adds a new mapflag `gear_lock` (`MF_GEAR_LOCK`) that prevents **manual** equipment changes on flagged maps.

## Behavior

- Equipping and unequipping by player action are blocked.
- Player receives message:
  - `A energia deste mapa impede a troca de equipamentos.`
- Forced unequip paths (`flag & 2`) are preserved so strip/break/forced removals still work.

## Included

- Source changes under `src/map/*`.
- Example mapflag file in `required files/conf/mapflag/gear_lock.conf`.
- Ready-to-apply patch in `actual .DIFF/MF_GEAR_LOCK [OK].DIFF`.
