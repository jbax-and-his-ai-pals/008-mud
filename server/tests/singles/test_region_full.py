# tests/singles/test_region_full.py
"""Coverage for engine/world/region.py's Region.from_dict() error handling
when an individual room entry fails to deserialize."""

import unittest

from engine.world.region import Region


class TestRegionFromDictRoomFailure(unittest.TestCase):
    def test_bad_room_entry_is_skipped_with_a_warning(self):
        data = {
            "name": "Broken Region",
            "description": "A region with a malformed room.",
            "rooms": {
                "good_room": {"name": "Good Room", "description": "Fine."},
                "bad_room": "not a dict, so item assignment raises TypeError",
            },
        }
        region = Region.from_dict(data)
        self.assertIn("good_room", region.rooms)
        self.assertNotIn("bad_room", region.rooms)


if __name__ == "__main__":
    unittest.main()
