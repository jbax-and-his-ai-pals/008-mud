# tests/singles/test_slice_geography.py
"""Where a door leads and where it leads back agree.

If room A has a compass exit `north` to B, then B must lead back to A, and by `south`. A gate that
opened onto the road while the courtyard that led to the gate had no way back made the map fold
back on itself; nothing checked it because each room only knows its own exits. This walks every
compass exit of the two adaptation slices, across regions, and holds each pair to opposites. Named
doors (`in`, `out`, `up`, `down`) are left alone: they are not a direction on the map.
"""

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OPPOSITE = {
    "north": "south", "south": "north", "east": "west", "west": "east",
    "up": "down", "down": "up", "in": "out", "out": "in",
    "northeast": "southwest", "southwest": "northeast", "northwest": "southeast", "southeast": "northwest",
}

COMPASS = {d for d in OPPOSITE if d not in ("up", "down", "in", "out")}


def _exits(set_id):
    """{(region, room): {direction: (region, room)}} for one content set."""
    found = {}
    for path in sorted((REPO_ROOT / "content_sets" / set_id / "data" / "regions").glob("*.json")):
        region = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(region.get("rooms"), dict):
            continue
        region_id = region.get("region_id", path.stem)
        for room_id, room in region["rooms"].items():
            targets = {}
            for direction, target in (room.get("exits") or {}).items():
                other_region, _, other_room = str(target).rpartition(":")
                targets[direction] = (other_region or region_id, other_room)
            found[(region_id, room_id)] = targets
    return found


class TestSliceGeography(unittest.TestCase):
    def check(self, set_id):
        rooms = _exits(set_id)
        problems = []
        for origin, exits in rooms.items():
            for direction, target in exits.items():
                if direction not in COMPASS or target not in rooms:
                    continue
                backs = {d: t for d, t in rooms[target].items() if t == origin}
                if not backs:
                    problems.append("%s --%s--> %s, but %s has no way back" % (
                        "%s:%s" % origin, direction, "%s:%s" % target, "%s:%s" % target))
                elif OPPOSITE[direction] not in backs and any(d in COMPASS for d in backs):
                    problems.append("%s --%s--> %s, but it leads back by %s (expected %s)" % (
                        "%s:%s" % origin, direction, "%s:%s" % target, ", ".join(backs), OPPOSITE[direction]))
        self.assertEqual([], problems)

    def test_ff4_slice(self):
        self.check("ff4_slice")

    def test_zelda_slice(self):
        self.check("zelda_slice")


if __name__ == "__main__":
    unittest.main()
