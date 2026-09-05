# tests/singles/test_definition_loader_full.py
"""Coverage for engine/world/definition_loader.py's edge branches: missing
template/region directories, non-.json files skipped, duplicate ids, missing
required fields, malformed JSON causing file_errors, load_all_definitions'
content_root mismatch guard, grant_starting_inventory's entry-shape handling,
and initialize_new_world's skip-existing-npc / failed-creation branches."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.world.definition_loader import (
    load_all_definitions,
    _load_item_templates,
    _load_npc_templates,
    _load_regions,
    grant_starting_inventory,
    initialize_new_world,
)
from engine.world.region import Region
from engine.world.room import Room


class TestLoadAllDefinitionsGuard(GameTestBase):
    def test_mismatched_content_root_raises(self):
        with self.assertRaises(TypeError):
            load_all_definitions(self.world, content_root="/some/other/path")


class TestLoadItemTemplates(GameTestBase):
    def setUp(self):
        super().setUp()
        self.tmp_root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        super().tearDown()

    def test_missing_directory_sets_dir_missing(self):
        stats = _load_item_templates(self.world, self.tmp_root)
        self.assertEqual(stats["dir_missing"], 1)

    def test_non_json_files_are_skipped(self):
        items_dir = os.path.join(self.tmp_root, "items")
        os.makedirs(items_dir)
        with open(os.path.join(items_dir, "readme.txt"), "w") as f:
            f.write("not json")
        stats = _load_item_templates(self.world, self.tmp_root)
        self.assertEqual(stats["files_loaded"], 0)

    def test_sets_json_is_skipped_as_metadata(self):
        items_dir = os.path.join(self.tmp_root, "items")
        os.makedirs(items_dir)
        with open(os.path.join(items_dir, "sets.json"), "w") as f:
            json.dump({"some_set": {}}, f)
        stats = _load_item_templates(self.world, self.tmp_root)
        self.assertEqual(stats["metadata_files_skipped"], 1)
        self.assertEqual(stats["files_loaded"], 0)

    def test_duplicate_ids_and_missing_required_fields_and_file_errors(self):
        items_dir = os.path.join(self.tmp_root, "items")
        os.makedirs(items_dir)
        with open(os.path.join(items_dir, "a.json"), "w") as f:
            json.dump({
                "sword": {"name": "Sword", "type": "Weapon"},
                "broken": {"name": "No Type"},
            }, f)
        with open(os.path.join(items_dir, "b.json"), "w") as f:
            json.dump({
                "sword": {"name": "Sword Again", "type": "Weapon"},
            }, f)
        with open(os.path.join(items_dir, "c.json"), "w") as f:
            f.write("{not valid json")

        stats = _load_item_templates(self.world, self.tmp_root)

        # c.json fails to parse, so it never reaches the files_loaded++ line.
        self.assertEqual(stats["files_loaded"], 2)
        self.assertEqual(stats["duplicate_ids"], 1)
        self.assertEqual(stats["invalid_missing_required"], 1)
        self.assertEqual(stats["file_errors"], 1)
        self.assertIn("sword", self.world.item_templates)
        self.assertNotIn("broken", self.world.item_templates)


class TestLoadNpcTemplates(GameTestBase):
    def setUp(self):
        super().setUp()
        self.tmp_root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        super().tearDown()

    def test_missing_directory_sets_dir_missing(self):
        stats = _load_npc_templates(self.world, self.tmp_root)
        self.assertEqual(stats["dir_missing"], 1)

    def test_non_json_files_are_skipped(self):
        npcs_dir = os.path.join(self.tmp_root, "npcs")
        os.makedirs(npcs_dir)
        with open(os.path.join(npcs_dir, "readme.txt"), "w") as f:
            f.write("not json")
        stats = _load_npc_templates(self.world, self.tmp_root)
        self.assertEqual(stats["files_loaded"], 0)

    def test_duplicate_ids_and_missing_name_and_file_errors(self):
        npcs_dir = os.path.join(self.tmp_root, "npcs")
        os.makedirs(npcs_dir)
        with open(os.path.join(npcs_dir, "a.json"), "w") as f:
            json.dump({
                "goblin": {"name": "Goblin"},
                "broken": {"description": "No name field"},
            }, f)
        with open(os.path.join(npcs_dir, "b.json"), "w") as f:
            json.dump({
                "goblin": {"name": "Goblin Again"},
            }, f)
        with open(os.path.join(npcs_dir, "c.json"), "w") as f:
            f.write("{not valid json")

        stats = _load_npc_templates(self.world, self.tmp_root)

        # c.json fails to parse, so it never reaches the files_loaded++ line.
        self.assertEqual(stats["files_loaded"], 2)
        self.assertEqual(stats["duplicate_ids"], 1)
        self.assertEqual(stats["invalid_missing_name"], 1)
        self.assertEqual(stats["file_errors"], 1)
        self.assertIn("goblin", self.world.npc_templates)
        self.assertNotIn("broken", self.world.npc_templates)


class TestLoadRegions(GameTestBase):
    def setUp(self):
        super().setUp()
        self.tmp_root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        super().tearDown()

    def test_missing_directory_logs_and_returns(self):
        _load_regions(self.world, self.tmp_root)
        self.assertEqual(self.world.regions, {})

    def test_malformed_region_file_causes_file_error_but_does_not_crash(self):
        regions_dir = os.path.join(self.tmp_root, "regions")
        os.makedirs(regions_dir)
        with open(os.path.join(regions_dir, "broken.json"), "w") as f:
            f.write("{not valid json")
        _load_regions(self.world, self.tmp_root)
        self.assertEqual(self.world.regions, {})


class TestGrantStartingInventory(GameTestBase):
    def test_non_list_entries_returns_immediately(self):
        grant_starting_inventory(self.world, self.player, entries="not a list")
        # No exception, nothing added -- just confirms the early return path.

    def test_string_entry_defaults_quantity_to_one(self):
        item_id = next(iter(self.world.item_templates))
        before = self.player.inventory.count_item(item_id)
        grant_starting_inventory(self.world, self.player, entries=[item_id])
        self.assertEqual(self.player.inventory.count_item(item_id), before + 1)

    def test_non_str_non_dict_entry_is_skipped(self):
        grant_starting_inventory(self.world, self.player, entries=[12345])

    def test_blank_item_id_is_skipped(self):
        grant_starting_inventory(self.world, self.player, entries=[{"item_id": "   "}])

    def test_unknown_item_id_logs_warning_and_is_skipped(self):
        grant_starting_inventory(self.world, self.player, entries=[{"item_id": "does_not_exist_xyz"}])

    def test_factory_failure_after_valid_template_lookup_grants_nothing(self):
        item_id = next(iter(self.world.item_templates))
        before = self.player.inventory.count_item(item_id)
        with patch("engine.world.definition_loader.ItemFactory.create_item_from_template", return_value=None):
            grant_starting_inventory(self.world, self.player, entries=[item_id])
        self.assertEqual(self.player.inventory.count_item(item_id), before)

    def test_dict_entry_with_quantity_grants_multiple_and_continues_loop(self):
        item_ids = list(self.world.item_templates.keys())[:2]
        grant_starting_inventory(
            self.world, self.player,
            entries=[{"item_id": item_ids[0], "quantity": 2}, {"item_id": item_ids[1]}],
        )
        self.assertGreaterEqual(self.player.inventory.count_item(item_ids[0]), 2)
        self.assertGreaterEqual(self.player.inventory.count_item(item_ids[1]), 1)


class TestInitializeNewWorldBranches(GameTestBase):
    def _make_region_with_room(self, region_id, room_id):
        region = Region(f"{region_id}-name", "test region", obj_id=region_id)
        room = Room(f"{room_id}-name", "test room", obj_id=room_id)
        region.add_room(room_id, room)
        self.world.add_region(region_id, region)
        return region, room

    def test_item_ref_missing_item_id_is_skipped(self):
        region, room = self._make_region_with_room("iw_region_a", "iw_room_a")
        room.initial_item_refs = [{}, None]
        initialize_new_world(self.world, "iw_region_a", "iw_room_a")
        self.assertEqual(room.items, [])

    def test_item_ref_with_invalid_template_creates_nothing(self):
        region, room = self._make_region_with_room("iw_region_b", "iw_room_b")
        room.initial_item_refs = [{"item_id": "totally_bogus_item_xyz"}]
        initialize_new_world(self.world, "iw_region_b", "iw_room_b")
        self.assertEqual(room.items, [])

    def test_npc_ref_missing_template_id_is_skipped(self):
        region, room = self._make_region_with_room("iw_region_c", "iw_room_c")
        room.initial_npc_refs = [{"instance_id": "no_template_here"}]
        initialize_new_world(self.world, "iw_region_c", "iw_room_c")
        self.assertNotIn("no_template_here", self.world.npcs)

    def test_npc_ref_with_existing_instance_id_is_not_recreated(self):
        # initialize_new_world resets world.npcs at the start of the call, so
        # a pre-existing NPC can't exercise this branch -- instead, two refs
        # in the same call share an instance_id; the second must be skipped.
        region, room = self._make_region_with_room("iw_region_d", "iw_room_d")
        room.initial_npc_refs = [
            {"template_id": "goblin", "instance_id": "dup_ghoul"},
            {"template_id": "goblin", "instance_id": "dup_ghoul"},
        ]
        # initialize_new_world spawns NPCs for every region in the world, so
        # count only calls carrying our own instance_id.
        from engine.npcs.npc_factory import NPCFactory
        original_create = NPCFactory.create_npc_from_template
        calls = []

        def counting_create(*args, **kwargs):
            if "dup_ghoul" in args or kwargs.get("instance_id") == "dup_ghoul":
                calls.append((args, kwargs))
            return original_create(*args, **kwargs)

        with patch.object(NPCFactory, "create_npc_from_template", side_effect=counting_create):
            initialize_new_world(self.world, "iw_region_d", "iw_room_d")

        self.assertEqual(len(calls), 1)
        self.assertIn("dup_ghoul", self.world.npcs)

    def test_npc_ref_with_invalid_template_creates_nothing(self):
        region, room = self._make_region_with_room("iw_region_e", "iw_room_e")
        room.initial_npc_refs = [{"template_id": "totally_bogus_npc_template_xyz", "instance_id": "iw_ghost"}]
        initialize_new_world(self.world, "iw_region_e", "iw_room_e")
        self.assertNotIn("iw_ghost", self.world.npcs)

    def test_skip_initial_player_leaves_player_none(self):
        self.world.skip_initial_player = True
        initialize_new_world(self.world, "iw_region_e", "iw_room_e")
        self.assertIsNone(self.world.player)
        self.world.skip_initial_player = False


if __name__ == "__main__":
    unittest.main()
