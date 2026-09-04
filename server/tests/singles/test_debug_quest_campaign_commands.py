# tests/singles/test_debug_quest_campaign_commands.py
"""Coverage for the GM/debug `quest` and `campaign` commands
(engine/commands/debug/quests.py), which were previously untested (5.5%
coverage) despite being reachable, real commands."""

from tests.fixtures import GameTestBase


def _two_stage_quest(quest_id: str) -> dict:
    return {
        "instance_id": quest_id,
        "title": "Test Quest",
        "type": "kill",
        "giver_instance_id": "quest_board",
        "current_stage_index": 0,
        "rewards": {"xp": 10},
        "objective": {"type": "kill", "target_template_id": "giant_rat", "required_quantity": 1},
        "stages": [
            {"stage_index": 0, "objective": {"type": "kill", "target_template_id": "giant_rat", "required_quantity": 1}},
            {"stage_index": 1, "objective": {"type": "kill", "target_template_id": "giant_rat", "required_quantity": 1}},
        ],
    }


def _one_stage_quest(quest_id: str) -> dict:
    return {
        "instance_id": quest_id,
        "title": "Test Quest",
        "type": "kill",
        "giver_instance_id": "quest_board",
        "current_stage_index": 0,
        "rewards": {"gold": 5},
        "objective": {"type": "kill", "target_template_id": "giant_rat", "required_quantity": 1},
        "stages": [
            {"stage_index": 0, "objective": {"type": "kill", "target_template_id": "giant_rat", "required_quantity": 1}},
        ],
    }


class TestDebugQuestCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("quest")
        self.assertIn("Usage", result)

    def test_list_with_no_active_quests(self):
        result = self.game.process_command("quest list")
        self.assertIn("No active quests", result)

    def test_list_shows_active_quests(self):
        self.player.runtime_state.quests.active["q1"] = _two_stage_quest("q1")
        result = self.game.process_command("quest list")
        self.assertIn("q1", result)

    def test_action_without_quest_id_shows_usage(self):
        result = self.game.process_command("quest advance")
        self.assertIn("Usage", result)

    def test_advance_unknown_quest_is_reported(self):
        result = self.game.process_command("quest advance nope")
        self.assertIn("not found in active log", result)

    def test_advance_moves_to_next_stage(self):
        self.player.runtime_state.quests.active["q1"] = _two_stage_quest("q1")
        result = self.game.process_command("quest advance q1")
        self.assertIn("Forced advancement", result)
        self.assertEqual(1, self.player.runtime_state.quests.active["q1"]["current_stage_index"])

    def test_advance_past_last_stage_forces_completion(self):
        self.player.runtime_state.quests.active["q1"] = _one_stage_quest("q1")
        result = self.game.process_command("quest advance q1")
        self.assertIn("Forced completion", result)
        self.assertNotIn("q1", self.player.runtime_state.quests.active)
        self.assertIn("q1", self.player.runtime_state.quests.completed)

    def test_complete_grants_rewards_and_removes_from_active(self):
        self.player.runtime_state.quests.active["q1"] = _one_stage_quest("q1")
        result = self.game.process_command("quest complete q1")
        self.assertIn("Forced completion", result)
        self.assertIn("5 Gold", result)
        self.assertNotIn("q1", self.player.runtime_state.quests.active)

    def test_unknown_subcommand(self):
        self.player.runtime_state.quests.active["q1"] = _one_stage_quest("q1")
        result = self.game.process_command("quest wobble q1")
        self.assertIn("Unknown subcommand", result)

    def test_quest_id_is_matched_by_partial_search(self):
        self.player.runtime_state.quests.active["quest_kill_rats_01"] = _one_stage_quest("quest_kill_rats_01")
        result = self.game.process_command("quest complete kill_rats")
        self.assertIn("Forced completion", result)


class TestDebugCampaignCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("campaign")
        self.assertIn("Usage", result)

    def test_list_shows_available_definitions_and_no_active(self):
        result = self.game.process_command("campaign list")
        self.assertIn("bandit_rebellion", result)
        self.assertIn("(None)", result)

    def test_list_shows_active_campaigns(self):
        self.player.runtime_state.quests.active_campaigns["bandit_rebellion"] = {"current_node": "intro_investigation"}
        result = self.game.process_command("campaign list")
        self.assertIn("intro_investigation", result)

    def test_start_requires_campaign_id(self):
        result = self.game.process_command("campaign start")
        self.assertIn("Usage", result)

    def test_start_unknown_campaign_fails(self):
        result = self.game.process_command("campaign start not_a_real_campaign")
        self.assertIn("Failed to start", result)

    def test_start_known_campaign_succeeds(self):
        result = self.game.process_command("campaign start bandit_rebellion")
        self.assertIn("Started campaign", result)
        self.assertIn("bandit_rebellion", self.player.runtime_state.quests.active_campaigns)

    def test_jump_requires_two_args(self):
        result = self.game.process_command("campaign jump bandit_rebellion")
        self.assertIn("Usage", result)

    def test_jump_on_inactive_campaign_fails(self):
        result = self.game.process_command("campaign jump bandit_rebellion confront_lieutenant")
        self.assertIn("is not active", result)

    def test_jump_to_unknown_node_fails(self):
        self.game.process_command("campaign start bandit_rebellion")
        result = self.game.process_command("campaign jump bandit_rebellion not_a_real_node")
        self.assertIn("not found", result)

    def test_jump_to_known_node_succeeds(self):
        self.game.process_command("campaign start bandit_rebellion")
        result = self.game.process_command("campaign jump bandit_rebellion confront_lieutenant")
        self.assertIn("Jumped campaign", result)
        self.assertEqual(
            "confront_lieutenant",
            self.player.runtime_state.quests.active_campaigns["bandit_rebellion"]["current_node"],
        )

    def test_unknown_subcommand(self):
        result = self.game.process_command("campaign wobble")
        self.assertIn("Unknown subcommand", result)
