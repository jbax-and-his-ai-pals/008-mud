# tests/singles/test_quest_command.py
"""Coverage for engine/commands/quest.py: look board, accept quest,
journal -- beyond what test_quests.py's kill/fetch/deliver lifecycle tests
already cover."""

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory


def _kill_quest(quest_id="q1", giver="quest_board"):
    objective = {"type": "kill", "target_template_id": "giant_rat", "required_quantity": 3}
    return {
        "instance_id": quest_id, "title": "Rat Extermination", "type": "kill",
        "giver_instance_id": giver, "current_stage_index": 0,
        "rewards": {"xp": 50, "gold": 10}, "state": "active",
        "objective": objective,
        "stages": [{"stage_index": 0, "objective": objective}],
    }


class _AtBoardTestBase(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.world.quest_manager.config["quest_board_locations"] = ["town:town_square"]


class TestLookBoardCommand(_AtBoardTestBase):
    def test_not_at_a_board_is_reported(self):
        self.world.quest_manager.config["quest_board_locations"] = []
        result = self.game.process_command("look board")
        self.assertIn("don't see a quest board", result)

    def test_empty_board_is_reported(self):
        self.world.quest_board = []
        result = self.game.process_command("look board")
        self.assertIn("currently empty", result)

    def test_lists_quests_with_giver_and_reward_and_quantity(self):
        self.world.quest_board = [_kill_quest("q1")]
        result = self.game.process_command("look board")
        self.assertIn("Rat Extermination", result)
        self.assertIn("(3)", result)
        self.assertIn("Quest Board Notice", result)
        self.assertIn("50 XP", result)
        self.assertIn("10 Gold", result)

    def test_lists_quest_with_named_npc_giver(self):
        from engine.npcs.npc_factory import NPCFactory
        elder = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="board_giver")
        self.world.add_npc(elder)
        self.world.quest_board = [_kill_quest("q1", giver="board_giver")]
        result = self.game.process_command("look board")
        self.assertIn(elder.name, result)


class TestAcceptQuestCommand(_AtBoardTestBase):
    def test_invalid_quest_number_is_rejected(self):
        self.world.quest_board = [_kill_quest("q1")]
        result = self.game.process_command("accept quest 5")
        self.assertIn("Invalid quest number", result)

    def test_accept_quest_two_word_form(self):
        self.world.quest_board = [_kill_quest("q1")]
        result = self.game.process_command("accept quest 1")
        self.assertIn("Quest Accepted", result)
        self.assertIn("q1", self.player.runtime_state.quests.active)

    def test_accept_bare_number_form(self):
        self.world.quest_board = [_kill_quest("q1")]
        result = self.game.process_command("accept 1")
        self.assertIn("Quest Accepted", result)

    def test_accept_deliver_quest_grants_package(self):
        objective = {
            "type": "deliver", "item_template_id": "item_starter_dagger",
            "item_instance_id": "pkg_001", "item_to_deliver_name": "Sealed Letter",
            "item_to_deliver_description": "A sealed letter.",
        }
        quest = {
            "instance_id": "q_deliver", "title": "Deliver the Letter", "type": "deliver",
            "giver_instance_id": "quest_board", "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective}],
        }
        self.world.quest_board = [quest]
        result = self.game.process_command("accept 1")
        self.assertIn("received the package", result)
        self.assertIsNotNone(self.player.inventory.find_item_by_id("pkg_001"))

    def test_accept_deliver_quest_fails_when_inventory_full(self):
        objective = {
            "type": "deliver", "item_template_id": "item_starter_dagger",
            "item_instance_id": "pkg_001", "item_to_deliver_name": "Sealed Letter",
            "item_to_deliver_description": "A sealed letter.",
        }
        quest = {
            "instance_id": "q_deliver", "title": "Deliver the Letter", "type": "deliver",
            "giver_instance_id": "quest_board", "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective}],
        }
        self.world.quest_board = [quest]
        self.player.inventory.max_weight = 0.001  # cannot fit anything
        result = self.game.process_command("accept 1")
        self.assertIn("Inventory full", result)
        self.assertEqual(1, len(self.world.quest_board))  # quest returned to board

    def test_no_args_falls_back_to_npc_offer(self):
        result = self.game.process_command("accept")
        # No offering NPC present in an otherwise-empty room.
        self.assertIn("No one here has offered", result)


class TestJournalCommand(_AtBoardTestBase):
    def test_empty_journal_is_reported(self):
        result = self.game.process_command("journal")
        self.assertEqual("Your quest journal is empty.", result)

    def test_completed_with_no_entries_is_reported(self):
        result = self.game.process_command("journal completed")
        self.assertEqual("You have not completed any quests yet.", result)

    def test_completed_lists_titles(self):
        self.player.runtime_state.quests.completed["q1"] = {"title": "Finished Quest"}
        result = self.game.process_command("journal completed")
        self.assertIn("Finished Quest", result)

    def test_active_kill_quest_shows_progress(self):
        objective = {
            "type": "kill", "current_quantity": 1, "required_quantity": 3,
            "target_name_plural": "Rats", "location_hint": "the sewers",
        }
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Rat Problem", "state": "active",
            "current_stage_index": 0, "giver_instance_id": "quest_board",
            "objective": objective, "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("journal")
        self.assertIn("Rat Problem", result)
        self.assertIn("1/3 Rats", result)
        self.assertIn("Quest Board", result)

    def test_active_group_kill_quest_shows_target_breakdown(self):
        objective = {
            "type": "group_kill",
            "targets": {
                "giant_rat": {"name": "Giant Rats", "required": 2, "current": 2},
                "goblin": {"name": "Goblins", "required": 1, "current": 0},
            },
        }
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Cull the Pests", "state": "active",
            "current_stage_index": 0, "giver_instance_id": "quest_board",
            "objective": objective, "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("journal")
        self.assertIn("Giant Rats: 2/2", result)
        self.assertIn("Goblins: 0/1", result)

    def test_active_fetch_quest_shows_inventory_count(self):
        ingot = ItemFactory.create_item_from_template("item_iron_ingot", self.world)
        self.player.inventory.add_item(ingot)
        objective = {
            "type": "fetch", "item_id": "item_iron_ingot", "required_quantity": 3,
            "item_name_plural": "Iron Ingots", "source_enemy_name_plural": "Golems",
            "location_hint": "the quarry",
        }
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Fetch Ingots", "state": "active",
            "current_stage_index": 0, "giver_instance_id": "quest_board",
            "objective": objective, "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("journal")
        self.assertIn("Gather 1/3 Iron Ingots", result)

    def test_active_deliver_quest_shows_package_status(self):
        objective = {
            "type": "deliver", "item_instance_id": "pkg_missing",
            "item_to_deliver_name": "Package", "recipient_name": "Someone",
            "recipient_location_description": "somewhere",
        }
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Deliver It", "state": "active",
            "current_stage_index": 0, "giver_instance_id": "quest_board",
            "objective": objective, "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("journal")
        self.assertIn("Deliver to: Someone", result)
        self.assertNotIn("Report to: Quest Board", result)
        self.assertIn("don't have the package", result)

    def test_active_quest_resolves_template_turn_in_giver_name(self):
        from engine.npcs.npc_factory import NPCFactory

        elder = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="journal_elder")
        self.world.add_npc(elder)
        objective = {"type": "scout"}
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Eyes in the Woods", "state": "active",
            "current_stage_index": 0, "giver_instance_id": "quest_board",
            "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective, "turn_in_id": "village_elder"}],
        }

        result = self.game.process_command("journal")

        self.assertIn(f"Report to: {elder.name}", result)
        self.assertNotIn("Report to: Unknown", result)

    def test_active_generic_objective_falls_back_to_stage_description(self):
        objective = {"type": "custom_thing"}
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Mystery Task", "state": "active",
            "current_stage_index": 0, "giver_instance_id": "quest_board",
            "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective, "description": "Do the thing."}],
        }
        result = self.game.process_command("journal")
        self.assertIn("Do the thing.", result)

    def test_ready_to_complete_quest_is_flagged(self):
        objective = {"type": "kill"}
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Almost Done", "state": "ready_to_complete",
            "current_stage_index": 0, "giver_instance_id": "quest_board",
            "objective": objective, "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("journal")
        self.assertIn("Ready to turn in!", result)

    def test_only_non_active_states_reports_no_active_quests(self):
        objective = {"type": "kill"}
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Archived-ish", "state": "abandoned",
            "current_stage_index": 0, "giver_instance_id": "quest_board",
            "objective": objective, "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("journal")
        self.assertEqual("You have no active quests.", result)
