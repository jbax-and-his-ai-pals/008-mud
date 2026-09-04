# tests/singles/test_instance_manager_full.py
"""Coverage for engine/world/instance_manager.py's guard clauses and error
paths in instantiate_quest_region/cleanup_quest_region, plus the entirely
untested _remove_links_to_region, check_and_cleanup_completed_instances,
and _cleanup_for_player -- most of which test_quest_instances.py's single
happy-path test never reaches."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.world.region import Region
from engine.world.room import Room
from engine.world.instance_manager import InstanceManager


def _quest_data(**overrides):
    data = {
        "instance_id": "im_test_quest",
        "entry_point": {"region_id": "town", "room_id": "town_square", "exit_command": "enter_place"},
        "instance_region": {
            "region_name": "Test Place", "region_description": "A place.",
            "rooms": {"entry": {"name": "Entry", "description": "x", "exits": {"out": "dynamic_exit"}}},
        },
        "objective": {"target_template_id": "goblin"},
        "layout_generation_config": {"target_count": [1, 1]},
    }
    data.update(overrides)
    return data


class TestResolveReferencePlayer(GameTestBase):
    def test_no_world_returns_none(self):
        im = InstanceManager(None)
        self.assertIsNone(im._resolve_reference_player())


class TestFindPlayerWithCompletedQuest(GameTestBase):
    def test_found_via_reference_player_fallback(self):
        im = self.world.instance_manager
        self.player.runtime_state.quests.completed["fallback_quest"] = {"state": "completed"}
        # Force the players-dict loop to find nothing, while
        # resolve_reference_player() (a separate lookup path) still
        # resolves to the real player -- exercising the fallback branch.
        with patch.object(self.world, "players", {}), \
             patch.object(self.world, "resolve_reference_player", return_value=self.player):
            result = im._find_player_with_completed_quest("fallback_quest")
        self.assertIs(self.player, result)

    def test_not_found_anywhere_returns_none(self):
        im = self.world.instance_manager
        self.assertIsNone(im._find_player_with_completed_quest("no_such_quest_anywhere"))


class TestInstantiateQuestRegionGuards(GameTestBase):
    def setUp(self):
        super().setUp()
        self.im = self.world.instance_manager

    def test_no_active_player_returns_false(self):
        self.world.players.clear()
        self.world._primary_player_id = None
        success, msg, giver_id = self.im.instantiate_quest_region(_quest_data())
        self.assertFalse(success)
        self.assertIn("without a player", msg)

    def test_missing_required_key_returns_false(self):
        data = _quest_data()
        del data["entry_point"]
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertFalse(success)
        self.assertIn("missing a required key", msg)

    def test_unexpected_exception_is_caught(self):
        data = _quest_data()
        with patch("engine.world.instance_manager.Region", side_effect=RuntimeError("boom")):
            success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertFalse(success)
        self.assertIn("unexpected error", msg.lower())

    def test_fully_qualified_exit_destination_is_left_unchanged(self):
        data = _quest_data(instance_region={
            "region_name": "Test Place", "region_description": "x",
            "rooms": {
                "entry": {"name": "Entry", "description": "x", "exits": {"out": "dynamic_exit", "side": "town:town_square"}},
            },
        })
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertTrue(success)
        new_region = self.world.regions[data["instance_region_id"]]
        self.assertEqual("town:town_square", new_region.get_room("entry").exits["side"])

    def test_bare_unqualified_exit_destination_gets_region_prefixed(self):
        data = _quest_data(instance_region={
            "region_name": "Test Place", "region_description": "x",
            "rooms": {
                "entry": {"name": "Entry", "description": "x", "exits": {"out": "dynamic_exit", "north": "second"}},
                "second": {"name": "Second", "description": "x", "exits": {}},
            },
        })
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertTrue(success)
        new_region = self.world.regions[data["instance_region_id"]]
        self.assertEqual(f"{data['instance_region_id']}:second", new_region.get_room("entry").exits["north"])

    def test_successful_spawn_of_all_creatures_completes_loop(self):
        data = _quest_data(
            layout_generation_config={"target_count": [2, 2]},
            instance_region={
                "region_name": "Test Place", "region_description": "x",
                "rooms": {
                    "entry": {"name": "Entry", "description": "x", "exits": {"out": "dynamic_exit"}},
                    "lair": {"name": "Lair", "description": "x", "exits": {}},
                },
            },
        )
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertTrue(success)
        spawned = [n for n in self.world.npcs.values() if n.current_region_id == data["instance_region_id"]]
        self.assertEqual(2, len(spawned))

    def test_no_target_template_id_returns_false(self):
        data = _quest_data(objective={})
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertFalse(success)
        self.assertIn("no target creature", msg)

    def test_no_spawnable_rooms_stops_spawn_loop_gracefully(self):
        # Only the entry room exists, so spawnable_room_ids is empty.
        data = _quest_data(layout_generation_config={"target_count": [3, 3]})
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertTrue(success)

    def test_npc_spawn_failure_cleans_up_and_returns_false(self):
        # Needs a second (non-entry) room so spawnable_room_ids isn't empty
        # and the spawn attempt actually runs (and fails) instead of
        # short-circuiting via the "no spawnable rooms" break.
        data = _quest_data(
            objective={"target_template_id": "not_a_real_template"},
            instance_region={
                "region_name": "Test Place", "region_description": "x",
                "rooms": {
                    "entry": {"name": "Entry", "description": "x", "exits": {"out": "dynamic_exit"}},
                    "spawn_room": {"name": "Spawn Room", "description": "x", "exits": {}},
                },
            },
        )
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertFalse(success)
        self.assertIn("Could not spawn required creature", msg)
        self.assertNotIn(data["instance_region_id"], self.world.regions)

    def test_missing_permanent_entry_region_returns_false(self):
        data = _quest_data(entry_point={"region_id": "not_a_real_region", "room_id": "x", "exit_command": "enter"})
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertFalse(success)
        self.assertIn("permanent entry region", msg)

    def test_missing_permanent_entry_room_still_succeeds_without_exit_link(self):
        data = _quest_data(entry_point={"region_id": "town", "room_id": "not_a_real_room", "exit_command": "enter"})
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertTrue(success)

    def test_giver_npc_created_successfully(self):
        self.world.npc_templates.setdefault("im_giver_template", {
            "name": "Quest Giver", "faction": "neutral",
        })
        data = _quest_data(giver_npc_template_id="im_giver_template")
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertTrue(success)
        self.assertIsNotNone(giver_id)
        self.assertIn(giver_id, self.world.npcs)

    def test_giver_npc_creation_failure_cleans_up_and_returns_false(self):
        data = _quest_data(giver_npc_template_id="not_a_real_giver_template")
        success, msg, giver_id = self.im.instantiate_quest_region(data)
        self.assertFalse(success)
        self.assertIn("Could not spawn giver NPC", msg)
        self.assertNotIn(data["instance_region_id"], self.world.regions)

    def test_giver_npc_creation_failure_with_no_permanent_room_skips_exit_removal(self):
        # entry_point room doesn't exist, so permanent_entry_room is None by
        # the time the giver-failure cleanup runs -- the exit-removal guard
        # must skip gracefully rather than raise.
        data = _quest_data(
            entry_point={"region_id": "town", "room_id": "not_a_real_room", "exit_command": "enter"},
            giver_npc_template_id="not_a_real_giver_template",
        )
        success, msg, giver_id = self.im.instantiate_quest_region(data)  # must not raise
        self.assertFalse(success)
        self.assertIn("Could not spawn giver NPC", msg)


class TestCleanupQuestRegion(GameTestBase):
    def setUp(self):
        super().setUp()
        self.im = self.world.instance_manager

    def test_no_active_player_and_no_fallback_is_a_no_op(self):
        self.world.players.clear()
        self.world._primary_player_id = None
        self.im.cleanup_quest_region("no_such_quest")  # must not raise

    def test_quest_not_in_completed_log_is_a_no_op(self):
        self.im.cleanup_quest_region("never_completed_quest", requesting_player=self.player)  # must not raise

    def test_cleanup_removes_permanent_exit_link(self):
        data = _quest_data(instance_id="cleanup_link_test")
        success, _msg, _gid = self.im.instantiate_quest_region(data)
        self.assertTrue(success)
        self.player.runtime_state.quests.completed["cleanup_link_test"] = data
        self.im.cleanup_quest_region("cleanup_link_test", requesting_player=self.player)
        town_square = self.world.get_region("town").get_room("town_square")
        self.assertNotIn("enter_place", town_square.exits)
        self.assertIn("cleanup_link_test", self.player.runtime_state.quests.archived)

    def test_cleanup_without_instance_region_or_entry_point_skips_that_step(self):
        self.player.runtime_state.quests.completed["bare_quest"] = {}
        self.im.cleanup_quest_region("bare_quest", requesting_player=self.player)
        self.assertIn("bare_quest", self.player.runtime_state.quests.archived)

    def test_cleanup_with_missing_permanent_region_skips_link_removal(self):
        quest_data = {
            "instance_region_id": "some_instance_region",
            "entry_point": {"region_id": "not_a_real_region", "room_id": "x", "exit_command": "enter"},
        }
        self.player.runtime_state.quests.completed["ghost_region_quest"] = quest_data
        self.im.cleanup_quest_region("ghost_region_quest", requesting_player=self.player)  # must not raise
        self.assertIn("ghost_region_quest", self.player.runtime_state.quests.archived)

    def test_cleanup_of_generated_saga_regions_removes_links_and_regions(self):
        gen_region = Region("Generated", "A generated saga region.", obj_id="saga_gen_region")
        gen_region.add_room("saga_entry", Room("Entry", "x", obj_id="saga_entry"))
        self.world.add_region("saga_gen_region", gen_region)

        town = self.world.get_region("town")
        town.get_room("town_square").exits["saga_link"] = "saga_gen_region:saga_entry"

        quest_data = {"generated_region_ids": ["saga_gen_region"]}
        self.player.runtime_state.quests.completed["saga_quest"] = quest_data
        self.im.cleanup_quest_region("saga_quest", requesting_player=self.player)

        self.assertNotIn("saga_gen_region", self.world.regions)
        self.assertNotIn("saga_link", town.get_room("town_square").exits)


class TestRemoveLinksToRegion(GameTestBase):
    def test_removes_only_exits_pointing_to_target_region(self):
        im = self.world.instance_manager
        town = self.world.get_region("town")
        square = town.get_room("town_square")
        square.exits["to_target"] = "target_region_x:some_room"
        square.exits["elsewhere"] = "town:town_square"
        im._remove_links_to_region("target_region_x")
        self.assertNotIn("to_target", square.exits)
        self.assertIn("elsewhere", square.exits)

    def test_skips_the_target_region_itself(self):
        im = self.world.instance_manager
        target_region = Region("Target", "x", obj_id="skip_self_region")
        room = Room("Room", "x", obj_id="room_a", exits={"loop": "skip_self_region:room_a"})
        target_region.add_room("room_a", room)
        self.world.add_region("skip_self_region", target_region)
        im._remove_links_to_region("skip_self_region")  # must not raise
        self.assertIn("loop", room.exits)


class TestCheckAndCleanupCompletedInstances(GameTestBase):
    def test_no_players_falls_back_to_reference_player(self):
        im = self.world.instance_manager
        original_players = dict(self.world.players)
        self.world.players.clear()
        try:
            with patch.object(self.world, "resolve_reference_player", return_value=self.player):
                im.check_and_cleanup_completed_instances()  # must not raise
        finally:
            self.world.players.update(original_players)

    def test_player_without_quests_state_is_skipped(self):
        im = self.world.instance_manager
        original = self.player.runtime_state.quests
        self.player.runtime_state.quests = None
        try:
            im.check_and_cleanup_completed_instances()  # must not raise
        finally:
            self.player.runtime_state.quests = original


class TestCleanupForPlayer(GameTestBase):
    def setUp(self):
        super().setUp()
        self.im = self.world.instance_manager

    def test_quest_without_regions_to_check_is_skipped(self):
        self.player.runtime_state.quests.completed["no_regions_quest"] = {}
        self.im._cleanup_for_player(self.player)
        self.assertIn("no_regions_quest", self.player.runtime_state.quests.completed)

    def test_player_still_in_instance_region_is_not_cleaned_up(self):
        self.player.runtime_state.quests.completed["still_inside_quest"] = {
            "instance_region_id": "still_inside_region",
        }
        self.player.current_region_id = "still_inside_region"
        self.im._cleanup_for_player(self.player)
        self.assertIn("still_inside_quest", self.player.runtime_state.quests.completed)

    def test_player_outside_instance_region_triggers_cleanup(self):
        data = _quest_data(instance_id="autoclean_quest")
        success, _msg, _gid = self.im.instantiate_quest_region(data)
        self.assertTrue(success)
        self.player.runtime_state.quests.completed["autoclean_quest"] = data
        self.player.current_region_id = "town"  # not the instance region
        self.im._cleanup_for_player(self.player)
        self.assertIn("autoclean_quest", self.player.runtime_state.quests.archived)

    def test_generated_region_ids_are_checked_too(self):
        self.player.runtime_state.quests.completed["gen_regions_quest"] = {
            "generated_region_ids": ["some_generated_region"],
        }
        self.player.current_region_id = "town"
        self.im._cleanup_for_player(self.player)
        self.assertIn("gen_regions_quest", self.player.runtime_state.quests.archived)


if __name__ == "__main__":
    import unittest
    unittest.main()
