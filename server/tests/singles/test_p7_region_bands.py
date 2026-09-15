"""P7's authored regional progression bands remain portable and usable."""

from engine.world.region import Region
from engine.world.room import Room
from engine.world.spawner import Spawner
from tests.fixtures import GameTestBase


class TestFantasyRegionBands(GameTestBase):
    EXPECTED_BANDS = {
        "town": (1, 3),
        "farmland": (1, 3),
        "forest": (1, 3),
        "coastal_path": (1, 3),
        "foothills": (2, 5),
        "swamp": (2, 4),
        "caves": (3, 6),
        "ruins": (3, 6),
        "mountains": (5, 8),
        "portbridge": (2, 4),
        "casino": (1, 3),
        "obsidian_trial": (6, 8),
    }

    def test_every_static_fantasy_region_has_its_authored_band(self):
        actual = {
            region_id: region.get_level_band()
            for region_id, region in self.world.regions.items()
            if region_id in self.EXPECTED_BANDS
        }
        self.assertEqual(self.EXPECTED_BANDS, actual)

    def test_spawner_uses_the_region_band_when_no_duplicate_range_is_authored(self):
        region = Region("A Remote Test Region", "No start-room distance is involved.", obj_id="remote_test")
        region.properties.update({"safe_zone": False, "level_band": {"min": 4, "max": 4}})
        region.add_room("clearing", Room("Clearing", "A quiet clearing.", obj_id="clearing"))
        region.spawner_config = {"monster_types": {"goblin": 1}}
        self.world.add_region(region.obj_id, region)

        Spawner(self.world)._spawn_monsters_in_region(region)

        spawned = [
            npc for npc in self.world.npcs.values()
            if npc.current_region_id == region.obj_id and npc.template_id == "goblin"
        ]
        self.assertEqual(1, len(spawned))
        self.assertEqual(4, spawned[0].level)
