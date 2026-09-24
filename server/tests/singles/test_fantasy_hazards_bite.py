"""Every fantasy_frontier hazard hurts a player at the level its region is for.

Hazard damage goes through `take_damage` (engine/world/environment.py), so a
flat `defense` (physical) or `magic_resist` (every other channel) comes off
each tick. The shipped numbers were written without that in mind: five of the
seven hazardous rooms did nothing at all to an unarmoured player at the bottom
of their region's level band, and the quicksand pit did nothing even at level 1.
This measures each room against a real player levelled to the top of the band.
"""

import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer
from engine.world import environment

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"
MINIMUM_BITE = 3


class TestFantasyHazardsBite(unittest.TestCase):
    def test_each_hazard_room_hurts_at_the_top_of_its_band(self):
        server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.addCleanup(server.shutdown)
        rooms = []
        for region_id, region in server.world.regions.items():
            band = region.properties.get("level_band") or {}
            for room_id, room in region.rooms.items():
                hazard = environment.hazard_in(server.world, room)
                if hazard is not None:
                    rooms.append((int(band.get("max", 1)), region_id, room_id, hazard))
        self.assertEqual(7, len(rooms), [r[1:3] for r in rooms])

        session = server.create_session(player_id="hazard_check")
        server.execute_command(session.session_id, "char create Rowan")
        player = server.get_player_for_session(session.session_id)
        level = 1
        for band_max, region_id, room_id, hazard in sorted(rooms, key=lambda r: r[0]):
            while level < band_max:
                player.level_up()
                level += 1
            player.health = player.max_health
            taken = player.take_damage(int(hazard["damage"]), hazard["channel"])
            with self.subTest(room=f"{region_id}:{room_id}", level=level):
                self.assertGreaterEqual(taken, MINIMUM_BITE, f"{hazard['id']} ({hazard['damage']} {hazard['channel']}) takes {taken} at level {level}")


if __name__ == "__main__":
    unittest.main()
