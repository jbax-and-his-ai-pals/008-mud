# tests/singles/test_quest_tracker.py
"""Coverage for engine/core/quests/tracker.py: handle_npc_killed's standard-
kill and group-kill objective tracking, and check_quest_completion's
clear_region auto-completion flow (including the completion-NPC respawn and
homeowner-returns message branches).

Note: _update_standard_kill's `if stages and idx < len(stages):` False arm
is left untested as unreachable -- handle_npc_killed only ever reaches
_update_standard_kill after manager.get_active_objective(quest_data)
returned a non-None objective, and that method itself requires `stages`
truthy and `idx` in-range to return anything at all, so both conditions
are already guaranteed true on the same quest_data by the time
_update_standard_kill re-checks them."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.core.quests.tracker import handle_npc_killed, check_quest_completion


def _goblin(world, instance_id="tracker_goblin"):
    npc = NPCFactory.create_npc_from_template("goblin", world, instance_id=instance_id)
    npc.template_id = "goblin"
    return npc


def _elder_giver(world, instance_id):
    # A non-"goblin"-templated NPC so it's never counted by a clear_region
    # objective targeting the "goblin" template.
    npc = NPCFactory.create_npc_from_template("village_elder", world, instance_id=instance_id)
    return npc


class TestHandleNpcKilled(GameTestBase):
    def test_missing_world_returns_none(self):
        qm = self.world.quest_manager
        original = qm.world
        qm.world = None
        try:
            self.assertIsNone(handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)}))
        finally:
            qm.world = original

    def test_missing_player_returns_none(self):
        qm = self.world.quest_manager
        self.assertIsNone(handle_npc_killed(qm, "npc_killed", {"player": None, "npc": _goblin(self.world)}))

    def test_missing_npc_returns_none(self):
        qm = self.world.quest_manager
        self.assertIsNone(handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": None}))

    def test_player_with_no_quests_state_returns_none(self):
        qm = self.world.quest_manager
        original = self.player.runtime_state.quests
        self.player.runtime_state.quests = None
        try:
            self.assertIsNone(handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)}))
        finally:
            self.player.runtime_state.quests = original

    def test_npc_without_template_id_returns_none(self):
        qm = self.world.quest_manager
        npc = _goblin(self.world)
        npc.template_id = None
        self.assertIsNone(handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": npc}))

    def test_non_active_quest_is_skipped(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["q1"] = {"state": "ready_to_complete"}
        self.assertIsNone(handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)}))

    def test_unrelated_objective_type_is_ignored(self):
        qm = self.world.quest_manager
        objective = {"type": "fetch", "item_id": "item_starter_dagger"}
        self.player.runtime_state.quests.active["q_fetch"] = {
            "state": "active", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIsNone(result)

    def test_group_kill_without_targets_key_is_ignored(self):
        qm = self.world.quest_manager
        objective = {"type": "group_kill"}
        self.player.runtime_state.quests.active["q_gk_no_targets"] = {
            "state": "active", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIsNone(result)

    def test_quest_with_no_objective_is_skipped(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["q2"] = {"state": "active", "stages": []}
        self.assertIsNone(handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)}))

    def test_kill_objective_mismatched_template_is_ignored(self):
        qm = self.world.quest_manager
        objective = {"type": "kill", "target_template_id": "some_other_mob", "current_quantity": 0, "required_quantity": 1}
        self.player.runtime_state.quests.active["q3"] = {
            "state": "active", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIsNone(result)
        self.assertEqual(0, objective["current_quantity"])

    def test_kill_objective_increments_and_reports_progress(self):
        qm = self.world.quest_manager
        objective = {"type": "kill", "target_template_id": "goblin", "current_quantity": 0, "required_quantity": 3}
        self.player.runtime_state.quests.active["q4"] = {
            "state": "active", "title": "Goblin Slaying", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIn("1/3 killed", result)
        self.assertEqual("active", self.player.runtime_state.quests.active["q4"]["state"])

    def test_kill_objective_completion_reports_ready_to_complete(self):
        qm = self.world.quest_manager
        objective = {"type": "kill", "target_template_id": "goblin", "current_quantity": 0, "required_quantity": 1}
        self.player.runtime_state.quests.active["q5"] = {
            "state": "active", "title": "Goblin Slaying", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective, "description": "Kill the goblin"}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIn("Objective complete", result)
        self.assertIn("Kill the goblin", result)
        self.assertEqual("ready_to_complete", self.player.runtime_state.quests.active["q5"]["state"])

    def test_group_kill_untracked_template_is_ignored(self):
        qm = self.world.quest_manager
        objective = {"type": "group_kill", "targets": {"some_other_mob": {"current": 0, "required": 1}}}
        self.player.runtime_state.quests.active["q6"] = {
            "state": "active", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIsNone(result)

    def test_group_kill_already_satisfied_target_does_not_increment(self):
        qm = self.world.quest_manager
        objective = {"type": "group_kill", "targets": {"goblin": {"current": 2, "required": 2, "name": "Goblin"}}}
        self.player.runtime_state.quests.active["q7"] = {
            "state": "active", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIsNone(result)
        self.assertEqual(2, objective["targets"]["goblin"]["current"])

    def test_group_kill_increments_and_reports_progress(self):
        qm = self.world.quest_manager
        objective = {
            "type": "group_kill",
            "targets": {
                "goblin": {"current": 0, "required": 2, "name": "Goblin"},
                "orc": {"current": 0, "required": 1, "name": "Orc"},
            },
        }
        self.player.runtime_state.quests.active["q8"] = {
            "state": "active", "title": "Clear the Camp", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIn("Goblin (1/2)", result)
        self.assertEqual("active", self.player.runtime_state.quests.active["q8"]["state"])

    def test_group_kill_all_targets_complete_reports_ready(self):
        qm = self.world.quest_manager
        objective = {
            "type": "group_kill",
            "targets": {"goblin": {"current": 0, "required": 1, "name": "Goblin"}},
        }
        self.player.runtime_state.quests.active["q9"] = {
            "state": "active", "title": "Clear the Camp", "objective": objective, "current_stage_index": 0,
            "stages": [{"objective": objective}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertIn("All targets eliminated", result)
        self.assertEqual("ready_to_complete", self.player.runtime_state.quests.active["q9"]["state"])

    def test_multiple_quest_messages_are_joined_with_newline(self):
        qm = self.world.quest_manager
        objective_a = {"type": "kill", "target_template_id": "goblin", "current_quantity": 0, "required_quantity": 5}
        objective_b = {"type": "kill", "target_template_id": "goblin", "current_quantity": 0, "required_quantity": 5}
        self.player.runtime_state.quests.active["qa"] = {
            "state": "active", "title": "A", "objective": objective_a, "current_stage_index": 0,
            "stages": [{"objective": objective_a}],
        }
        self.player.runtime_state.quests.active["qb"] = {
            "state": "active", "title": "B", "objective": objective_b, "current_stage_index": 0,
            "stages": [{"objective": objective_b}],
        }
        result = handle_npc_killed(qm, "npc_killed", {"player": self.player, "npc": _goblin(self.world)})
        self.assertEqual(2, result.count("\n") + 1)


class TestCheckQuestCompletion(GameTestBase):
    def test_missing_world_is_a_no_op(self):
        qm = self.world.quest_manager
        original = qm.world
        qm.world = None
        try:
            check_quest_completion(qm)  # must not raise
        finally:
            qm.world = original

    def test_explicit_player_with_no_quests_state_is_skipped(self):
        qm = self.world.quest_manager
        original = self.player.runtime_state.quests
        self.player.runtime_state.quests = None
        try:
            check_quest_completion(qm, self.player)  # must not raise
        finally:
            self.player.runtime_state.quests = original

    def test_falls_back_to_world_players_when_no_explicit_player(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["clear_q"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
        }
        check_quest_completion(qm, None)  # must not raise, uses world.players
        # No hostiles alive in "town" matching "goblin" -> should complete.
        self.assertEqual("ready_to_complete", self.player.runtime_state.quests.active["clear_q"]["state"])

    def test_falls_back_to_resolve_reference_player_when_no_players_dict_entries(self):
        # World.players is truly empty (world.player itself is a computed
        # property backed by this same dict) -> the elif's falsy branch is
        # taken and resolve_reference_player() is consulted as a fallback,
        # which here also has nothing to resolve, so nothing runs.
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["clear_q2"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
        }
        self.world.player = None
        check_quest_completion(qm, None)  # must not raise
        self.assertEqual("active", self.player.runtime_state.quests.active["clear_q2"]["state"])

    def test_resolve_reference_player_fallback_is_used_when_available(self):
        # world.players is empty (elif is falsy) but resolve_reference_player
        # is patched to still find someone -- exercises the true arm of
        # "if fallback_player is not None".
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["clear_q3"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
        }
        self.world.player = None
        with patch.object(self.world, "resolve_reference_player", return_value=self.player):
            check_quest_completion(qm, None)
        self.assertEqual("ready_to_complete", self.player.runtime_state.quests.active["clear_q3"]["state"])

    def test_multiple_players_are_all_processed(self):
        from engine.player.core import Player
        qm = self.world.quest_manager
        other = Player("Other Hero", obj_id="tracker_other_hero", world=self.world)
        other.world = self.world
        other.current_region_id = self.player.current_region_id
        other.current_room_id = self.player.current_room_id
        self.world.players[other.obj_id] = other
        other.runtime_state.quests.active["other_clear_q"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
        }
        self.player.runtime_state.quests.active["main_clear_q"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
        }
        check_quest_completion(qm, None)
        self.assertEqual("ready_to_complete", self.player.runtime_state.quests.active["main_clear_q"]["state"])
        self.assertEqual("ready_to_complete", other.runtime_state.quests.active["other_clear_q"]["state"])

    def test_no_game_renderer_skips_message_but_still_completes(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["clear_no_game"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
        }
        original_game = self.world.game
        self.world.game = None
        try:
            check_quest_completion(qm, self.player)
        finally:
            self.world.game = original_game
        self.assertEqual("ready_to_complete", self.player.runtime_state.quests.active["clear_no_game"]["state"])

    def test_giver_prefixed_but_not_present_in_npcs_skips_deletion(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["clear_ghost_giver"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
            "giver_instance_id": "giver_never_actually_spawned",
        }
        check_quest_completion(qm, self.player)  # must not raise
        self.assertEqual(
            "ready_to_complete", self.player.runtime_state.quests.active["clear_ghost_giver"]["state"],
        )

    def test_non_active_quest_is_skipped(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["skip1"] = {"state": "ready_to_complete", "completion_check_enabled": True}
        check_quest_completion(qm, self.player)  # must not raise

    def test_completion_check_disabled_is_skipped(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["skip2"] = {"state": "active", "completion_check_enabled": False}
        check_quest_completion(qm, self.player)  # must not raise

    def test_non_clear_region_objective_is_skipped(self):
        qm = self.world.quest_manager
        objective = {"type": "kill", "target_template_id": "goblin"}
        self.player.runtime_state.quests.active["skip3"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": objective, "current_stage_index": 0, "stages": [{"objective": objective}],
        }
        check_quest_completion(qm, self.player)
        self.assertEqual("active", self.player.runtime_state.quests.active["skip3"]["state"])

    def test_missing_instance_region_id_is_skipped(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["skip4"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
        }
        check_quest_completion(qm, self.player)
        self.assertEqual("active", self.player.runtime_state.quests.active["skip4"]["state"])

    def test_hostiles_still_remaining_is_skipped(self):
        qm = self.world.quest_manager
        goblin = _goblin(self.world, "still_alive_goblin")
        goblin.current_region_id = "town"
        goblin.is_alive = True
        self.world.add_npc(goblin)
        self.player.runtime_state.quests.active["still_active"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
        }
        check_quest_completion(qm, self.player)
        self.assertEqual("active", self.player.runtime_state.quests.active["still_active"]["state"])

    def test_clear_region_completion_sends_message_via_renderer(self):
        qm = self.world.quest_manager
        self.world.npc_templates["completion_giver_template"] = {"name": "The Homeowner"}
        self.game.renderer.clear()
        self.player.runtime_state.quests.active["clear_msg"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin", "completion_npc_template_id": "completion_giver_template"},
            "instance_region_id": "town",
            "meta_instance_data": {"instance_region": {"region_name": "Goblin Den"}},
        }
        check_quest_completion(qm, self.player)
        joined = "\n".join(self.game.renderer.message_buffer)
        self.assertIn("cleared the Goblin Den", joined)
        self.assertIn("The Homeowner", joined)

    def test_clear_region_completion_without_completion_npc_template_uses_generic_label(self):
        qm = self.world.quest_manager
        self.game.renderer.clear()
        self.player.runtime_state.quests.active["clear_generic"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
        }
        check_quest_completion(qm, self.player)
        joined = "\n".join(self.game.renderer.message_buffer)
        self.assertIn("the quest giver", joined)

    def test_original_giver_prefixed_giver_is_removed_and_replaced(self):
        qm = self.world.quest_manager
        giver = _elder_giver(self.world, "giver_original_npc")
        giver.current_region_id = "town"
        self.world.add_npc(giver)
        self.world.npc_templates["completion_replacement_template"] = {"name": "Replacement Giver"}

        self.player.runtime_state.quests.active["clear_replace"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {
                "type": "clear_region", "target_template_id": "goblin",
                "completion_npc_template_id": "completion_replacement_template",
            },
            "instance_region_id": "town",
            "giver_instance_id": "giver_original_npc",
            "meta_instance_data": {
                "entry_point": {"region_id": "town", "room_id": "town_square"},
            },
        }
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        check_quest_completion(qm, self.player)

        # The replacement NPC is created with the same instance id as the
        # original giver, so the key is reoccupied rather than absent --
        # what matters is that it's now the completion-template NPC.
        replaced = self.world.npcs.get("giver_original_npc")
        self.assertIsNotNone(replaced)
        self.assertEqual("completion_replacement_template", replaced.template_id)
        joined = "\n".join(self.game.renderer.message_buffer)
        self.assertIn("homeowner returns", joined)

    def test_giver_replacement_without_matching_player_room_sends_no_homeowner_message(self):
        qm = self.world.quest_manager
        giver = _elder_giver(self.world, "giver_original_npc2")
        giver.current_region_id = "town"
        self.world.add_npc(giver)
        self.world.npc_templates["completion_replacement_template2"] = {"name": "Replacement Giver 2"}

        self.player.runtime_state.quests.active["clear_replace2"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {
                "type": "clear_region", "target_template_id": "goblin",
                "completion_npc_template_id": "completion_replacement_template2",
            },
            "instance_region_id": "town",
            "giver_instance_id": "giver_original_npc2",
            "meta_instance_data": {
                "entry_point": {"region_id": "somewhere_else", "room_id": "somewhere_else_room"},
            },
        }
        self.game.renderer.clear()
        check_quest_completion(qm, self.player)
        joined = "\n".join(self.game.renderer.message_buffer)
        self.assertNotIn("homeowner returns", joined)

    def test_giver_not_prefixed_is_left_alone(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["clear_no_prefix"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
            "giver_instance_id": "not_prefixed_id",
        }
        check_quest_completion(qm, self.player)  # must not raise
        self.assertEqual("ready_to_complete", self.player.runtime_state.quests.active["clear_no_prefix"]["state"])

    def test_giver_replacement_skipped_when_no_completion_npc_template(self):
        qm = self.world.quest_manager
        giver = _elder_giver(self.world, "giver_no_template")
        giver.current_region_id = "town"
        self.world.add_npc(giver)
        self.player.runtime_state.quests.active["clear_no_template"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {"type": "clear_region", "target_template_id": "goblin"},
            "instance_region_id": "town",
            "giver_instance_id": "giver_no_template",
        }
        check_quest_completion(qm, self.player)
        self.assertNotIn("giver_no_template", self.world.npcs)

    def test_giver_replacement_with_unknown_completion_template_creates_no_npc(self):
        qm = self.world.quest_manager
        giver = _elder_giver(self.world, "giver_bad_template")
        giver.current_region_id = "town"
        self.world.add_npc(giver)
        self.player.runtime_state.quests.active["clear_bad_template"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {
                "type": "clear_region", "target_template_id": "goblin",
                "completion_npc_template_id": "not_a_real_completion_template",
            },
            "instance_region_id": "town",
            "giver_instance_id": "giver_bad_template",
            "meta_instance_data": {"entry_point": {"region_id": "town", "room_id": "town_square"}},
        }
        count_before = len(self.world.npcs)
        check_quest_completion(qm, self.player)
        # The original giver is deleted, but no replacement can be created.
        self.assertEqual(count_before - 1, len(self.world.npcs))

    def test_giver_replacement_skipped_when_entry_point_missing(self):
        qm = self.world.quest_manager
        giver = _elder_giver(self.world, "giver_no_entry")
        giver.current_region_id = "town"
        self.world.add_npc(giver)
        self.world.npc_templates["completion_no_entry_template"] = {"name": "No Entry Giver"}
        self.player.runtime_state.quests.active["clear_no_entry"] = {
            "state": "active", "completion_check_enabled": True,
            "objective": {
                "type": "clear_region", "target_template_id": "goblin",
                "completion_npc_template_id": "completion_no_entry_template",
            },
            "instance_region_id": "town",
            "giver_instance_id": "giver_no_entry",
        }
        check_quest_completion(qm, self.player)
        self.assertFalse(any(n.template_id == "completion_no_entry_template" for n in self.world.npcs.values()))


if __name__ == "__main__":
    import unittest
    unittest.main()
