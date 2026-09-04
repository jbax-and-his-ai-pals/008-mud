# tests/singles/test_quest_generator.py
"""Coverage for engine/core/quest_generation/generator.py's QuestGenerator:
generate_noninstance_quest's guard clauses and type dispatch,
generate_instance_quest's candidate-filtering branches, _select_giver_npc,
_generate_random_house_layout, and instantiate_quest's procedural-region
generation/linking, reward generation, and the per-stage objective-template
branches (group_kill/kill/fetch_procedural/scout) plus turn-in-npc selection
and description templating -- almost none of which the existing
instance-manager/quest-manager tests reach, since those mock the generator
out entirely."""

from unittest.mock import patch, MagicMock

from tests.fixtures import GameTestBase
from engine.core.quest_generation.generator import QuestGenerator
from engine.npcs.npc_factory import NPCFactory
from engine.world.region import Region
from engine.world.room import Room


def _isolate_giver_pool(world):
    """fantasy_frontier's default world already has NPCs interested in
    generic quests (e.g. the blacksmith wants 'kill' givers) and quest_board
    'instance' templates. Clear both pools so a test's own fixtures are the
    only candidates the generator can find."""
    world.npcs.clear()
    world.quest_manager.npc_interests.clear()


def _quest_giver(world, quest_type, instance_id="quest_giver_npc"):
    world.npc_templates.setdefault("quest_giver_template", {
        "name": "Quest Giver", "faction": "neutral",
        "properties": {"can_give_generic_quests": True},
    })
    npc = NPCFactory.create_npc_from_template("quest_giver_template", world, instance_id=instance_id)
    npc.template_id = "quest_giver_template"
    npc.properties["can_give_generic_quests"] = True
    world.add_npc(npc)
    world.quest_manager.npc_interests["quest_giver_template"] = [quest_type]
    return npc


class TestGenerateNoninstanceQuest(GameTestBase):
    def setUp(self):
        super().setUp()
        self.gen = self.world.quest_manager.generator

    def test_no_world_returns_none(self):
        original = self.gen.world
        self.gen.world = None
        try:
            self.assertIsNone(self.gen.generate_noninstance_quest(1, "kill"))
        finally:
            self.gen.world = original

    def test_no_giver_found_returns_none(self):
        _isolate_giver_pool(self.world)
        self.assertIsNone(self.gen.generate_noninstance_quest(1, "kill"))

    def test_giver_npc_vanished_returns_none(self):
        _quest_giver(self.world, "kill")
        with patch.object(self.world, "get_npc", return_value=None):
            self.assertIsNone(self.gen.generate_noninstance_quest(1, "kill"))

    def test_unrecognized_quest_type_yields_no_objective_and_returns_none(self):
        _quest_giver(self.world, "unrecognized_type")
        self.assertIsNone(self.gen.generate_noninstance_quest(1, "unrecognized_type"))

    def test_objective_generation_failure_returns_none(self):
        _quest_giver(self.world, "kill")
        with patch("engine.core.quest_generation.generator.generate_kill_objective", return_value=None):
            self.assertIsNone(self.gen.generate_noninstance_quest(1, "kill"))

    def test_kill_type_dispatches_to_kill_objective(self):
        _quest_giver(self.world, "kill")
        fake_objective = {"target_template_id": "goblin", "required_quantity": 1}
        with patch("engine.core.quest_generation.generator.generate_kill_objective", return_value=fake_objective) as mock_kill:
            quest = self.gen.generate_noninstance_quest(1, "kill")
        mock_kill.assert_called_once()
        self.assertIsNotNone(quest)
        self.assertEqual("kill", quest["stages"][0]["objective"]["type"])

    def test_fetch_type_dispatches_to_fetch_objective(self):
        _quest_giver(self.world, "fetch")
        fake_objective = {"item_id": "item_starter_dagger"}
        with patch("engine.core.quest_generation.generator.generate_fetch_objective", return_value=fake_objective) as mock_fetch:
            quest = self.gen.generate_noninstance_quest(1, "fetch")
        mock_fetch.assert_called_once()
        self.assertIsNotNone(quest)

    def test_deliver_type_dispatches_to_deliver_objective(self):
        _quest_giver(self.world, "deliver")
        fake_objective = {"recipient_instance_id": "someone"}
        with patch("engine.core.quest_generation.generator.generate_deliver_objective", return_value=fake_objective) as mock_deliver:
            quest = self.gen.generate_noninstance_quest(1, "deliver")
        mock_deliver.assert_called_once()
        self.assertIsNotNone(quest)

    def test_random_quest_type_chosen_when_not_specified(self):
        _isolate_giver_pool(self.world)
        giver = _quest_giver(self.world, "kill")
        fake_objective = {"target_template_id": "goblin"}
        # random.choice is called twice: once to pick the quest type, once
        # inside _select_giver_npc to pick among matching givers.
        with patch(
            "engine.core.quest_generation.generator.random.choice",
            side_effect=["kill", giver.obj_id],
        ), patch("engine.core.quest_generation.generator.generate_kill_objective", return_value=fake_objective):
            quest = self.gen.generate_noninstance_quest(1, None)
        self.assertIsNotNone(quest)


class TestSelectGiverNpc(GameTestBase):
    def setUp(self):
        super().setUp()
        self.gen = self.world.quest_manager.generator

    def test_no_world_returns_none(self):
        original = self.gen.world
        self.gen.world = None
        try:
            self.assertIsNone(self.gen._select_giver_npc("kill"))
        finally:
            self.gen.world = original

    def test_npc_without_template_id_is_skipped(self):
        _isolate_giver_pool(self.world)
        npc = _quest_giver(self.world, "kill", "giver_notemplate")
        npc.template_id = None
        self.assertIsNone(self.gen._select_giver_npc("kill"))

    def test_no_matching_givers_returns_none(self):
        _isolate_giver_pool(self.world)
        _quest_giver(self.world, "fetch")  # only interested in fetch
        self.assertIsNone(self.gen._select_giver_npc("kill"))

    def test_matching_giver_is_selected(self):
        _isolate_giver_pool(self.world)
        npc = _quest_giver(self.world, "kill")
        self.assertEqual(npc.obj_id, self.gen._select_giver_npc("kill"))


class TestGenerateInstanceQuest(GameTestBase):
    def setUp(self):
        super().setUp()
        self.gen = self.world.quest_manager.generator
        # fantasy_frontier ships real "instance"-type quest templates (e.g.
        # a house-infestation bounty); clear them so each test controls
        # exactly which templates the generator can pick from.
        self.world.quest_manager.quest_templates.clear()

    def test_no_valid_instance_templates_returns_none(self):
        self.assertIsNone(self.gen.generate_instance_quest(1))

    def test_template_above_player_level_is_excluded(self):
        self.world.quest_manager.quest_templates["high_level_instance"] = {
            "type": "instance", "level": 50,
            "objective": {"possible_target_template_ids": ["goblin"]},
        }
        self.assertIsNone(self.gen.generate_instance_quest(1))

    def test_no_possible_creatures_returns_none(self):
        self.world.quest_manager.quest_templates["empty_creatures"] = {
            "type": "instance", "level": 1, "objective": {"possible_target_template_ids": []},
        }
        self.assertIsNone(self.gen.generate_instance_quest(1))

    def test_no_valid_entry_points_returns_none(self):
        self.world.quest_manager.quest_templates["no_entry"] = {
            "type": "instance", "level": 1,
            "objective": {"possible_target_template_ids": ["goblin"]},
            "possible_entry_regions": ["not_a_real_region"],
        }
        self.assertIsNone(self.gen.generate_instance_quest(1))

    def test_region_lookup_miss_is_skipped_in_entry_point_search(self):
        self.world.quest_manager.quest_templates["mixed_regions"] = {
            "type": "instance", "level": 1,
            "objective": {"possible_target_template_ids": ["goblin"]},
            "possible_entry_regions": ["not_a_real_region", "town"],
        }
        with patch.object(self.world, "is_location_outdoors", return_value=True):
            quest = self.gen.generate_instance_quest(1)
        self.assertIsNotNone(quest)

    def test_successful_generation_builds_full_quest_data(self):
        self.world.quest_manager.quest_templates["full_instance"] = {
            "type": "instance", "level": 1,
            "objective": {"possible_target_template_ids": ["goblin"]},
            "possible_entry_regions": ["town"],
            "layout_generation_config": {"min_rooms": 2, "max_rooms": 2},
            "rewards": {"xp": 200},
        }
        with patch.object(self.world, "is_location_outdoors", return_value=True):
            quest = self.gen.generate_instance_quest(1)
        self.assertIsNotNone(quest)
        self.assertEqual("instance", quest["type"])
        self.assertEqual({"xp": 200}, quest["rewards"])
        self.assertIn("meta_instance_data", quest)


class TestGenerateRandomHouseLayout(GameTestBase):
    def test_layout_has_linked_rooms(self):
        gen = self.world.quest_manager.generator
        layout = gen._generate_random_house_layout({"min_rooms": 3, "max_rooms": 3, "possible_room_names": ["Den"]})
        self.assertEqual(3, len(layout["rooms"]))
        self.assertIn("out", layout["rooms"]["room_0"]["exits"])
        self.assertEqual("room_0", layout["rooms"]["room_1"]["exits"]["south"])
        self.assertEqual("room_1", layout["rooms"]["room_0"]["exits"]["north"])


class TestInstantiateQuestLogicProceduralRegions(GameTestBase):
    def setUp(self):
        super().setUp()
        self.gen = self.world.quest_manager.generator

    def _fake_region(self, region_id="generated_region"):
        region = Region("Generated", "A generated place.", obj_id=region_id)
        region.add_room("entry", Room("Entry", "The entry.", obj_id="entry"))
        return region

    def test_procedural_region_generated_and_linked(self):
        template = {
            "procedural_regions": [
                {
                    "id_key": "dungeon_id", "theme": "caves", "rooms": 3,
                    "entry_point": {"region": "town", "room": "town_square"},
                }
            ],
        }
        fake_region = self._fake_region()
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            MockGen.return_value.generate_region.return_value = (fake_region, "entry")
            result = self.gen.instantiate_quest(template, 1)
        self.assertIn("generated_region_ids", result)
        self.assertIn(fake_region.obj_id, result["generated_region_ids"])
        town_square = self.world.get_region("town").get_room("town_square")
        self.assertIn("enter_quest", town_square.exits)
        self.assertIn("exit_quest", fake_region.get_room("entry").exits)

    def test_multiple_procedural_regions_are_all_processed(self):
        template = {
            "procedural_regions": [
                {"id_key": "region_a", "theme": "caves", "rooms": 3},
                {"id_key": "region_b", "theme": "ruins", "rooms": 3},
            ],
        }
        region_a = self._fake_region("region_a_generated")
        region_b = self._fake_region("region_b_generated")
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            MockGen.return_value.generate_region.side_effect = [(region_a, "entry"), (region_b, "entry")]
            result = self.gen.instantiate_quest(template, 1)
        self.assertEqual(
            {"region_a_generated", "region_b_generated"}, set(result["generated_region_ids"]),
        )

    def test_procedural_region_generation_failure_is_skipped(self):
        template = {"procedural_regions": [{"theme": "caves", "rooms": 3}]}
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            MockGen.return_value.generate_region.return_value = None
            result = self.gen.instantiate_quest(template, 1)
        self.assertNotIn("generated_region_ids", result)

    def test_procedural_region_without_entry_point_skips_linking(self):
        template = {"procedural_regions": [{"theme": "caves", "rooms": 3}]}
        fake_region = self._fake_region("no_link_region")
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            MockGen.return_value.generate_region.return_value = (fake_region, "entry")
            result = self.gen.instantiate_quest(template, 1)
        self.assertIn("no_link_region", result["generated_region_ids"])

    def test_procedural_region_entry_point_with_unknown_parent_region_skips_linking(self):
        template = {
            "procedural_regions": [
                {"theme": "caves", "rooms": 3, "entry_point": {"region": "not_a_real_region"}},
            ],
        }
        fake_region = self._fake_region("orphan_region")
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            MockGen.return_value.generate_region.return_value = (fake_region, "entry")
            result = self.gen.instantiate_quest(template, 1)  # must not raise
        self.assertIn("orphan_region", result["generated_region_ids"])

    def test_procedural_region_missing_entry_room_object_skips_exit_quest_link(self):
        template = {
            "procedural_regions": [
                {"theme": "caves", "rooms": 3, "entry_point": {"region": "town", "room": "town_square"}},
            ],
        }
        fake_region = self._fake_region("mismatched_entry_region")
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            # entry_room_id "not_a_real_room" doesn't exist in fake_region,
            # so new_region.get_room(...) returns None.
            MockGen.return_value.generate_region.return_value = (fake_region, "not_a_real_room")
            result = self.gen.instantiate_quest(template, 1)
        town_square = self.world.get_region("town").get_room("town_square")
        # The parent-side link is still made...
        self.assertIn("enter_quest", town_square.exits)
        # ...but the reverse exit_quest link on the generated side is skipped.
        self.assertIn("mismatched_entry_region", result["generated_region_ids"])

    def test_procedural_region_entry_point_with_missing_parent_room_skips_linking(self):
        template = {
            "procedural_regions": [
                {"theme": "caves", "rooms": 3, "entry_point": {"region": "town", "room": "not_a_real_room"}},
            ],
        }
        fake_region = self._fake_region("dangling_region")
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            MockGen.return_value.generate_region.return_value = (fake_region, "entry")
            result = self.gen.instantiate_quest(template, 1)  # must not raise
        self.assertIn("dangling_region", result["generated_region_ids"])

    def test_entry_point_room_defaults_via_random_choice_when_room_not_specified(self):
        template = {
            "procedural_regions": [
                {"theme": "caves", "rooms": 3, "entry_point": {"region": "town"}},
            ],
        }
        fake_region = self._fake_region("auto_room_region")
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            MockGen.return_value.generate_region.return_value = (fake_region, "entry")
            result = self.gen.instantiate_quest(template, 1)
        town_region = self.world.get_region("town")
        # Some room in town should now have the enter_quest exit.
        self.assertTrue(any("enter_quest" in room.exits for room in town_region.rooms.values()))


class TestInstantiateQuestLogicRewards(GameTestBase):
    def setUp(self):
        super().setUp()
        self.gen = self.world.quest_manager.generator

    def test_gold_and_xp_ranges_generate_rewards(self):
        template = {"generate_rewards": {"gold_range": [5, 5], "xp_range": [10, 10]}}
        with patch("engine.core.quest_generation.generator.random.randint", return_value=5):
            result = self.gen.instantiate_quest(template, 1)
        self.assertEqual(5, result["rewards"]["gold"])

    def test_generate_item_success_adds_generated_item_data(self):
        template = {"generate_rewards": {"generate_item": {"base_template_id": "item_starter_dagger"}}}
        fake_item = MagicMock()
        fake_item.to_dict.return_value = {"obj_id": "generated_dagger"}
        with patch("engine.core.quest_generation.generator.LootGenerator.generate_loot", return_value=fake_item):
            result = self.gen.instantiate_quest(template, 5)
        self.assertEqual({"obj_id": "generated_dagger"}, result["rewards"]["generated_item_data"])

    def test_generate_item_failure_omits_generated_item_data(self):
        template = {"generate_rewards": {"generate_item": {"base_template_id": "item_starter_dagger"}}}
        with patch("engine.core.quest_generation.generator.LootGenerator.generate_loot", return_value=None):
            result = self.gen.instantiate_quest(template, 5)
        self.assertNotIn("generated_item_data", result["rewards"])


class TestInstantiateQuestLogicStages(GameTestBase):
    def setUp(self):
        super().setUp()
        self.gen = self.world.quest_manager.generator

    def test_target_region_placeholder_is_resolved_from_saga_context(self):
        template = {
            "procedural_regions": [{"id_key": "dungeon", "theme": "caves", "rooms": 3}],
            "stages": [{"objective": {"target_region": "{dungeon}", "type": "scout"}}],
        }
        fake_region = Region("Generated", "x", obj_id="dungeon_region_1")
        fake_region.add_room("entry", Room("Entry", "x", obj_id="entry"))
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockGen:
            MockGen.return_value.generate_region.return_value = (fake_region, "entry")
            result = self.gen.instantiate_quest(template, 1)
        self.assertEqual("dungeon_region_1", result["stages"][0]["objective"]["target_region"])

    def test_group_kill_targets_config_expands_into_targets_dict(self):
        template = {
            "stages": [{
                "objective": {
                    "type": "group_kill",
                    "targets_config": {
                        "monster_pool": ["goblin"], "total_types": 1, "count_per_type_range": [2, 2],
                    },
                },
            }],
        }
        result = self.gen.instantiate_quest(template, 1)
        objective = result["stages"][0]["objective"]
        self.assertNotIn("targets_config", objective)
        self.assertIn("goblin", objective["targets"])
        self.assertEqual(2, objective["targets"]["goblin"]["required"])

    def test_kill_target_config_with_pool_selects_target(self):
        template = {
            "stages": [{
                "objective": {"type": "kill", "target_config": {"monster_pool": ["goblin"], "count": 3}},
            }],
        }
        result = self.gen.instantiate_quest(template, 1)
        objective = result["stages"][0]["objective"]
        self.assertEqual("goblin", objective["target_template_id"])
        self.assertEqual(3, objective["required_quantity"])

    def test_kill_target_config_with_empty_pool_is_a_no_op(self):
        template = {
            "stages": [{"objective": {"type": "kill", "target_config": {"monster_pool": []}}}],
        }
        result = self.gen.instantiate_quest(template, 1)
        objective = result["stages"][0]["objective"]
        self.assertNotIn("target_template_id", objective)

    def test_fetch_procedural_generates_item_name_and_flags(self):
        template = {
            "stages": [{
                "objective": {
                    "type": "fetch_procedural", "base_template_id": "item_ancient_amulet",
                    "name_pattern": "Artifact of {Noun}",
                },
            }],
        }
        with patch("engine.core.quest_generation.generator.random.choice", side_effect=["Shining", "Truth"]):
            result = self.gen.instantiate_quest(template, 1)
        objective = result["stages"][0]["objective"]
        self.assertEqual("fetch", objective["type"])
        self.assertTrue(objective["is_procedural_item"])
        self.assertEqual("Artifact of Truth", objective["item_name"])

    def test_scout_with_matching_keyword_finds_room(self):
        town = self.world.get_region("town")
        town.add_room("unique_belltower_xyz", Room("Belltower", "High up.", obj_id="unique_belltower_xyz"))
        template = {
            "stages": [{
                "objective": {
                    "type": "scout", "target_region": "town",
                    "target_room_keywords": ["unique_belltower_xyz"],
                },
            }],
        }
        result = self.gen.instantiate_quest(template, 1)
        objective = result["stages"][0]["objective"]
        self.assertEqual("unique_belltower_xyz", objective["target_room_id"])
        self.assertIn("Belltower", objective["location_hint"])

    def test_scout_without_keywords_picks_any_room(self):
        template = {
            "stages": [{"objective": {"type": "scout", "target_region": "town"}}],
        }
        result = self.gen.instantiate_quest(template, 1)
        objective = result["stages"][0]["objective"]
        self.assertNotEqual("unknown", objective["target_room_id"])

    def test_scout_with_empty_region_and_no_keywords_falls_back_to_all_rooms_list(self):
        from engine.world.region import Region as RegionCls
        empty_region = RegionCls("Empty Region", "No rooms at all.", obj_id="empty_scout_region")
        self.world.add_region("empty_scout_region", empty_region)
        template = {
            "stages": [{"objective": {"type": "scout", "target_region": "empty_scout_region"}}],
        }
        result = self.gen.instantiate_quest(template, 1)
        objective = result["stages"][0]["objective"]
        self.assertEqual("unknown", objective["target_room_id"])

    def test_scout_with_unknown_region_falls_back_to_unknown(self):
        template = {
            "stages": [{"objective": {"type": "scout", "target_region": "not_a_real_region"}}],
        }
        result = self.gen.instantiate_quest(template, 1)
        objective = result["stages"][0]["objective"]
        self.assertEqual("unknown", objective["target_room_id"])
        self.assertEqual("Unknown Location", objective["location_hint"])

    def test_turn_in_same_as_previous_reuses_prior_npc(self):
        elder = self.world.get_npc(list(self.world.npcs.keys())[0]) if self.world.npcs else None
        template = {
            "stages": [
                {"objective": {"type": "talk"}, "turn_in_id": "explicit_npc_1"},
                {"objective": {"type": "talk"}, "turn_in_config": "SAME_AS_PREVIOUS"},
            ],
        }
        result = self.gen.instantiate_quest(template, 1)
        self.assertEqual("explicit_npc_1", result["stages"][1]["turn_in_id"])

    def test_turn_in_config_dict_selects_matching_npc(self):
        npc = _quest_giver(self.world, "kill", "turn_in_candidate")
        npc.current_region_id = "town"
        template = {
            "stages": [{
                "objective": {"type": "talk"},
                "turn_in_config": {"npc_pool_faction": "neutral", "npc_pool_region": "town"},
            }],
        }
        with patch("engine.core.quest_generation.generator.random.choice", return_value="turn_in_candidate"):
            result = self.gen.instantiate_quest(template, 1)
        self.assertEqual("turn_in_candidate", result["stages"][0]["turn_in_id"])

    def test_turn_in_config_dict_with_no_candidates_falls_back_to_quest_board(self):
        template = {
            "stages": [{
                "objective": {"type": "talk"},
                "turn_in_config": {"npc_pool_faction": "no_such_faction_exists"},
            }],
        }
        result = self.gen.instantiate_quest(template, 1)
        self.assertEqual("quest_board", result["stages"][0]["turn_in_id"])

    def test_turn_in_config_dict_skips_dead_npcs(self):
        npc = _quest_giver(self.world, "kill", "dead_candidate")
        npc.is_alive = False
        template = {
            "stages": [{
                "objective": {"type": "talk"},
                "turn_in_config": {"npc_pool_faction": "neutral"},
            }],
        }
        result = self.gen.instantiate_quest(template, 1)
        self.assertNotEqual("dead_candidate", result["stages"][0]["turn_in_id"])

    def test_description_template_is_formatted_from_saga_context(self):
        template = {
            "stages": [{
                "objective": {"type": "fetch_procedural", "name_pattern": "{Noun}"},
                "description": "Find the {item_name}.",
            }],
        }
        with patch("engine.core.quest_generation.generator.random.choice", side_effect=["Ancient", "Hope"]):
            result = self.gen.instantiate_quest(template, 1)
        self.assertIn("Find the", result["stages"][0]["description"])
        self.assertNotIn("{item_name}", result["stages"][0]["description"])

    def test_description_template_with_missing_key_is_left_unformatted(self):
        template = {
            "stages": [{
                "objective": {"type": "talk"},
                "description": "This needs {a_key_that_will_never_exist}.",
            }],
        }
        result = self.gen.instantiate_quest(template, 1)
        self.assertEqual("This needs {a_key_that_will_never_exist}.", result["stages"][0]["description"])


if __name__ == "__main__":
    import unittest
    unittest.main()
