# MAX_MSG_5000 [OK]

Raises the map-server message table limit from `MAP_MAX_MSG 2500` to `MAP_MAX_MSG 5000` in `src/map/map.cpp`.

## Notes
- This increases available map message IDs for future systems that use `map_msg.conf`.
- Existing behavior remains unchanged aside from the larger upper bound.
