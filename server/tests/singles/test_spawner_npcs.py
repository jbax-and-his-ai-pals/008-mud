# tests/singles/test_spawner_npcs.py
"""Coverage for Spawner's wandering (friendly/neutral) NPC spawning --
the ambient counterpart to hostile monster spawning added alongside it.
Mirrors test_spawner_full.py's structure for the monster side."""

import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.world.spawner import Spawner
from engine.world.region import Region
from engine.world.room import Room


class TestSpawnNpcsInRegion(GameTestBase):
    def setUp(self):
        super().setUp()
        self.spawner = Spawner(self.world)
        self.region = Region("NPC Zone", "Testing", obj_id="spawner_npc_zone")
        self.world.add_region("spawner_npc_zone", self.region)
        if "villager" not in self.world.npc_templates:
            self.world.npc_templates["villager"] = {
                "name": "Villager", "description": "Friendly.", "faction": "neutral", "health": 10,
            }

    def test_wandering_npc_spawns_in_a_suitable_room(self):
        room = Room("Square", "A square.", obj_id="npc_room")
        self.region.add_room("npc_room", room)
        self.region.spawner_config = {"npc_types": {"villager": 1}}
        self.spawner._spawn_npcs_in_region(self.region)
        villagers = [n for n in self.world.npcs.values() if n.current_region_id == self.region.obj_id]
        self.assertEqual(len(villagers), 1)
        self.assertEqual(villagers[0].current_room_id, "npc_room")

    def test_safe_zone_does_not_block_npc_spawning(self):
        room = Room("Square", "A square.", obj_id="npc_room")
        self.region.add_room("npc_room", room)
        self.region.properties["safe_zone"] = True
        self.region.spawner_config = {"npc_types": {"villager": 1}}
        self.spawner._spawn_npcs_in_region(self.region)
        villagers = [n for n in self.world.npcs.values() if n.current_region_id == self.region.obj_id]
        self.assertEqual(len(villagers), 1)

    def test_npcs_enabled_false_blocks_spawning(self):
        room = Room("Square", "A square.", obj_id="npc_room")
        self.region.add_room("npc_room", room)
        self.region.spawner_config = {"npc_types": {"villager": 1}, "npcs_enabled": False}
        self.spawner._spawn_npcs_in_region(self.region)
        villagers = [n for n in self.world.npcs.values() if n.current_region_id == self.region.obj_id]
        self.assertEqual(len(villagers), 0)

    def test_monsters_enabled_false_does_not_affect_npc_spawning(self):
        room = Room("Square", "A square.", obj_id="npc_room")
        self.region.add_room("npc_room", room)
        self.region.properties["safe_zone"] = False
        self.region.spawner_config = {
            "npc_types": {"villager": 1}, "monster_types": {}, "monsters_enabled": False,
        }
        self.spawner._spawn_npcs_in_region(self.region)
        villagers = [n for n in self.world.npcs.values() if n.current_region_id == self.region.obj_id]
        self.assertEqual(len(villagers), 1)

    def test_no_npc_spawn_flagged_room_is_excluded(self):
        blocked_room = Room("Private Yard", "No wandering here.", obj_id="blocked_room")
        blocked_room.update_property("no_npc_spawn", True)
        self.region.add_room("blocked_room", blocked_room)
        self.region.spawner_config = {"npc_types": {"villager": 1}}
        self.spawner._spawn_npcs_in_region(self.region)
        villagers = [n for n in self.world.npcs.values() if n.current_region_id == self.region.obj_id]
        self.assertEqual(len(villagers), 0)

    def test_empty_npc_type_weights_returns_without_spawning(self):
        room = Room("Square", "A square.", obj_id="npc_room")
        self.region.add_room("npc_room", room)
        self.region.spawner_config = {"npc_types": {}}
        self.spawner._spawn_npcs_in_region(self.region)  # must not raise
        villagers = [n for n in self.world.npcs.values() if n.current_region_id == self.region.obj_id]
        self.assertEqual(len(villagers), 0)

    def test_wandering_cap_blocks_further_spawns(self):
        room = Room("Square", "A square.", obj_id="npc_room")
        self.region.add_room("npc_room", room)
        self.region.spawner_config = {"npc_types": {"villager": 1}}
        with patch.object(self.spawner, "_count_wandering_npcs_in_region", return_value=999):
            self.spawner._spawn_npcs_in_region(self.region)
        villagers = [n for n in self.world.npcs.values() if n.current_region_id == self.region.obj_id]
        self.assertEqual(len(villagers), 0)

    def test_unknown_npc_template_returns_without_spawning(self):
        room = Room("Square", "A square.", obj_id="npc_room")
        self.region.add_room("npc_room", room)
        self.region.spawner_config = {"npc_types": {"totally_bogus_npc_xyz": 1}}
        self.spawner._spawn_npcs_in_region(self.region)
        spawned = [n for n in self.world.npcs.values() if n.template_id == "totally_bogus_npc_xyz"]
        self.assertEqual(len(spawned), 0)


class TestSpawnerUpdateCallsBothSpawnFunctions(GameTestBase):
    def test_update_calls_both_monster_and_npc_spawning(self):
        spawner = Spawner(self.world)
        with patch.object(spawner, "_spawn_monsters_in_region") as mock_monsters, \
             patch.object(spawner, "_spawn_npcs_in_region") as mock_npcs, \
             patch("engine.world.spawner.random.random", return_value=0.0):
            region = Region("Both Zone", "Testing", obj_id="spawner_both_zone")
            self.world.add_region("spawner_both_zone", region)
            self.player.current_region_id = "spawner_both_zone"
            spawner.update(time.time())
        mock_monsters.assert_called_once()
        mock_npcs.assert_called_once()


if __name__ == "__main__":
    unittest.main()
