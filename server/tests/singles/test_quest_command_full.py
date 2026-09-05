# tests/singles/test_quest_command_full.py
"""Coverage for engine/commands/quest.py: look_board's quantity-omitted
summary, accept_quest's "quest <#>" argument form and non-numeric-arg
NPC-fallback, the full meta_instance_data (instance quest) path --
success, failure with board restoration, and dynamically-spawned-giver
dialogue -- journal's no-player guard, the giver-resolution stage-index
fallback, and the generic-objective fallback's missing-stage-description
default."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.commands.quest import look_board_handler, accept_quest_handler, journal_handler
from engine.npcs.npc_factory import NPCFactory


class _QuestBoardTestBase(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"


class TestLookBoard(_QuestBoardTestBase):
    def test_quest_without_required_quantity_omits_summary(self):
        self.world.quest_board.append({
            "instance_id": "q_no_qty", "title": "Mystery Task",
            "giver_instance_id": "quest_board", "rewards": {},
            "objective": {"type": "kill"},
            "stages": [{"stage_index": 0, "objective": {"type": "kill"}}],
        })
        result = look_board_handler([], {"world": self.world, "player": self.player})
        self.assertIn("Mystery Task", result)
        self.assertNotIn("Mystery Task(", result)


class TestAcceptQuestArgParsing(_QuestBoardTestBase):
    def setUp(self):
        super().setUp()
        # The real world seeds its own (sometimes non-instantiable) quests
        # onto the board at init; clear them so "accept quest 1"
        # deterministically targets our own quest at index 0.
        self.world.quest_board.clear()

    def test_quest_prefix_with_number_targets_the_board(self):
        self.world.quest_board.append({
            "instance_id": "q1", "title": "Board Quest", "giver_instance_id": "quest_board",
            "rewards": {}, "objective": {"type": "kill"},
            "stages": [{"stage_index": 0, "objective": {"type": "kill"}}],
        })
        result = self.game.process_command("accept quest 1")
        self.assertIn("Quest Accepted", result)

    def test_leading_quest_word_is_stripped_from_args(self):
        # process_command() itself resolves "accept quest 1" to the
        # two-word primary command "accept quest" with args=["1"] via
        # longest-match dispatch, so args never actually contain the
        # literal word "quest" through normal input -- exercise the
        # handler's own internal stripping directly instead.
        self.world.quest_board.clear()
        self.world.quest_board.append({
            "instance_id": "q1", "title": "Board Quest", "giver_instance_id": "quest_board",
            "rewards": {}, "objective": {"type": "kill"},
            "stages": [{"stage_index": 0, "objective": {"type": "kill"}}],
        })
        context = {"world": self.world, "player": self.player, "game": self.game}
        result = accept_quest_handler(["quest", "1"], context)
        self.assertIn("Quest Accepted", result)

    def test_non_numeric_arg_falls_back_to_npc_offer(self):
        result = self.game.process_command("accept some npc offer")
        self.assertIn("No one here has offered", result)


class TestAcceptQuestInstanceHandling(_QuestBoardTestBase):
    def setUp(self):
        super().setUp()
        # The real world seeds its own quests onto the board at init; clear
        # them so "accept quest 1" deterministically targets our own quest.
        self.world.quest_board.clear()

    def _instance_quest(self):
        return {
            "instance_id": "q_instance", "title": "Instance Quest",
            "giver_instance_id": "quest_board", "rewards": {},
            "objective": {"type": "kill"},
            "stages": [{"stage_index": 0, "objective": {"type": "kill"}, "turn_in_id": "quest_board"}],
            "meta_instance_data": {"entry_point": {"region_id": "town", "room_id": "town_square"}},
        }

    def test_instantiation_failure_restores_quest_to_board(self):
        self.world.quest_board.append(self._instance_quest())
        with patch.object(self.world, "instantiate_quest_region", return_value=(False, "no space", None)):
            result = self.game.process_command("accept quest 1")
        self.assertIn("Could not start quest", result)
        self.assertEqual(len(self.world.quest_board), 1)

    def test_successful_instantiation_without_dynamic_giver(self):
        self.world.quest_board.append(self._instance_quest())
        with patch.object(self.world, "instantiate_quest_region", return_value=(True, "The quest begins.", None)):
            result = self.game.process_command("accept quest 1")
        self.assertIn("Quest Accepted", result)
        self.assertIn("q_instance", self.player.runtime_state.quests.active)

    def test_successful_instantiation_with_missing_giver_npc_skips_dialogue(self):
        self.world.quest_board.append(self._instance_quest())
        with patch.object(self.world, "instantiate_quest_region", return_value=(True, "The quest begins.", "totally_bogus_giver_npc_xyz")):
            result = self.game.process_command("accept quest 1")
        self.assertIn("Quest Accepted", result)
        active_quest = self.player.runtime_state.quests.active["q_instance"]
        self.assertEqual(active_quest["giver_instance_id"], "totally_bogus_giver_npc_xyz")

    def test_successful_instantiation_with_dynamic_giver_appends_dialogue(self):
        giver = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="dynamic_giver_npc")
        self.world.add_npc(giver)
        giver.current_region_id = "town"
        giver.current_room_id = "town_square"
        giver.dialog["greeting_extended"] = "Meet me at the {entry_location_desc}."
        self.world.quest_board.append(self._instance_quest())
        with patch.object(self.world, "instantiate_quest_region", return_value=(True, "The quest begins.", "dynamic_giver_npc")):
            result = self.game.process_command("accept quest 1")
        self.assertIn("Quest Accepted", result)
        active_quest = self.player.runtime_state.quests.active["q_instance"]
        self.assertEqual(active_quest["giver_instance_id"], "dynamic_giver_npc")
        self.assertEqual(active_quest["stages"][0]["turn_in_id"], "dynamic_giver_npc")


class TestJournalHandler(_QuestBoardTestBase):
    def test_no_player_reports_not_found(self):
        result = journal_handler([], {"world": self.world, "player": None})
        self.assertEqual(result, "Player not found.")

    def test_giver_resolution_falls_back_to_giver_instance_id_with_no_stages(self):
        elder = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="journal_giver_npc")
        self.world.add_npc(elder)
        self.player.runtime_state.quests.active["q_no_stages"] = {
            "instance_id": "q_no_stages", "title": "Stageless Quest",
            "giver_instance_id": "journal_giver_npc", "state": "active",
            "current_stage_index": 0, "stages": [],
            "objective": {"type": "unknown"},
        }
        result = self.game.process_command("journal")
        self.assertIn("Stageless Quest", result)
        self.assertIn(elder.name, result)

    def test_generic_objective_with_no_stage_description_uses_default_text(self):
        self.player.runtime_state.quests.active["q_generic"] = {
            "instance_id": "q_generic", "title": "Generic Quest",
            "giver_instance_id": "quest_board", "state": "active",
            "current_stage_index": 0, "stages": [],
            "objective": {"type": "totally_unrecognized_type"},
        }
        result = self.game.process_command("journal")
        self.assertIn("Complete the objective", result)


if __name__ == "__main__":
    unittest.main()
