# tests/singles/test_save_v4_to_v5.py
"""A save written before the world snapshot still loads, meaning what it always meant.

Version 5 keeps the world's state under one `world` key (world_snapshot.py). A
version 4 file kept NPCs, room items, dynamic regions, the quest board, the respawn
queue and the time and weather as separate top-level keys. Someone's character is in
one of those files, so the migration is tested against a file in the old shape, not
against a v5 file that happens to be re-labelled.
"""

import json
import os
import unittest

from engine.items.item_factory import ItemFactory
from engine.world.save_format import SAVE_FORMAT_VERSION, migrate
from engine.world.save_manager import SaveManager
from tests.fixtures import GameTestBase


def _version_4(payload):
    """What a version 4 writer produced, built from a version 5 file's contents."""
    world = payload.pop("world")
    payload["save_format_version"] = 4
    payload["npc_states"] = world["npcs"]
    payload["room_items_state"] = world["room_items"]["rooms"]
    payload["dynamic_regions"] = world["dynamic_regions"]
    payload["quest_board"] = world["quest_board"]
    payload["respawn_queue"] = world["respawn_queue"]
    payload["time_state"] = world["time"]
    payload["weather_state"] = world["weather"]
    return payload


class TestMigration(unittest.TestCase):
    def _legacy(self):
        return {
            "save_format_version": 4,
            "player": {"name": "Old"},
            "npc_states": {"npc_1": {"template_id": "goblin"}},
            "room_items_state": {"town:town_square": [{"item_id": "item_healing_potion_small"}]},
            "dynamic_regions": [{"obj_id": "dynamic_x"}],
            "quest_board": [{"id": "q"}],
            "respawn_queue": [{"instance_id": "a", "respawn_time": 1234.5}],
            "time_state": {"game_time": 9.0},
            "weather_state": {"weather": "rain"},
        }

    def test_the_current_version_is_five(self):
        self.assertEqual(5, SAVE_FORMAT_VERSION)

    def test_a_version_4_file_moves_under_world_and_loses_its_old_keys(self):
        migrated, applied = migrate(self._legacy())
        self.assertEqual(["_migrate_4_to_5"], applied)
        for old in ("npc_states", "room_items_state", "dynamic_regions", "quest_board", "respawn_queue", "time_state", "weather_state"):
            self.assertNotIn(old, migrated)
        world = migrated["world"]
        self.assertEqual({"npc_1": {"template_id": "goblin"}}, world["npcs"])
        self.assertEqual("full", world["room_items"]["mode"], "a v4 file named every room that held something")
        self.assertEqual({"town:town_square": [{"item_id": "item_healing_potion_small"}]}, world["room_items"]["rooms"])
        self.assertEqual([{"obj_id": "dynamic_x"}], world["dynamic_regions"])
        self.assertEqual({"game_time": 9.0}, world["time"])
        self.assertEqual({"weather": "rain"}, world["weather"])
        self.assertIsNone(world["clock"], "a v4 respawn time is an absolute reading, so there is nothing to rebase against")
        self.assertEqual([{"instance_id": "a", "respawn_time": 1234.5}], world["respawn_queue"])
        self.assertEqual({"name": "Old"}, migrated["player"], "the player is not this migration's business")

    def test_a_file_with_none_of_the_old_keys_migrates_to_an_empty_world(self):
        migrated, _ = migrate({"save_format_version": 4, "player": {}})
        self.assertEqual({}, migrated["world"]["npcs"])
        self.assertEqual({"mode": "full", "rooms": {}}, migrated["world"]["room_items"])


class TestLoadingAVersion4File(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = SaveManager(self.world)
        self.save_file = "save_v4_to_v5_test.json"
        self.save_path = os.path.join(self.world.save_directory, self.save_file)
        self.addCleanup(lambda: os.path.exists(self.save_path) and os.remove(self.save_path))

    def _room(self, room_id):
        return self.world.regions[self.player.current_region_id].get_room(room_id)

    def test_a_version_4_file_loads_and_a_room_it_does_not_list_is_empty(self):
        region = self.player.current_region_id
        listed = self.player.current_room_id
        other = next(rid for rid in self.world.regions[region].rooms if rid != listed)
        self._room(listed).items = [ItemFactory.create_item_from_template("item_healing_potion_small", self.world)]
        self._room(other).items = []
        self.assertTrue(self.manager.save(self.save_file))
        with open(self.save_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        with open(self.save_path, "w", encoding="utf-8") as handle:
            json.dump(_version_4(payload), handle)

        # The world moves on: something new on the floor of a room the save never named.
        self._room(other).items = [ItemFactory.create_item_from_template("item_healing_potion_small", self.world)]
        self._room(listed).items = []

        success, _time, _weather = self.manager.load(self.save_file)
        self.assertTrue(success)
        self.assertEqual(["item_healing_potion_small"], [item.obj_id for item in self._room(listed).items])
        self.assertEqual([], self._room(other).items, "legacy meaning: a room the file does not list holds nothing")


if __name__ == "__main__":
    unittest.main()
