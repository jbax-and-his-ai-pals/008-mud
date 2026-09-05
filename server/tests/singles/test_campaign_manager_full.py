# tests/singles/test_campaign_manager_full.py
"""Coverage for engine/campaign/campaign_manager.py: __init__'s data_root
mismatch guard, _load_definitions' missing-directory/non-json-skip/
malformed-file branches, start_campaign's already-active-or-completed
guard and missing-start-node guard, handle_quest_completion's unknown-
node guard, missing-player-state skip, empty-transitions fallthrough,
FAILURE-trigger matching, a failed RNG-chance roll skipping a transition,
missing-player-state on the advance path, the "path ends here" fallback,
and _trigger_node's non-QUEST/non-END no-op and END-without-active-state
skip."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.campaign.campaign_manager import CampaignManager
from engine.campaign.campaign_models import CampaignDefinition, CampaignNode, CampaignTransition


class TestInit(GameTestBase):
    def test_mismatched_data_root_raises(self):
        with self.assertRaises(ValueError):
            CampaignManager(self.world, data_root="/some/other/path")


class TestLoadDefinitions(GameTestBase):
    def setUp(self):
        super().setUp()
        self.tmp_root = tempfile.mkdtemp()
        self.original_data_root = self.world.data_root
        self.world.data_root = self.tmp_root

    def tearDown(self):
        self.world.data_root = self.original_data_root
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        super().tearDown()

    def test_missing_directory_results_in_no_definitions(self):
        manager = CampaignManager(self.world, data_root=self.tmp_root)
        self.assertEqual(manager.definitions, {})

    def test_non_json_files_are_skipped(self):
        campaigns_dir = os.path.join(self.tmp_root, "campaigns")
        os.makedirs(campaigns_dir)
        with open(os.path.join(campaigns_dir, "readme.txt"), "w") as f:
            f.write("not json")
        manager = CampaignManager(self.world, data_root=self.tmp_root)
        self.assertEqual(manager.definitions, {})

    def test_malformed_json_file_is_logged_and_skipped(self):
        campaigns_dir = os.path.join(self.tmp_root, "campaigns")
        os.makedirs(campaigns_dir)
        with open(os.path.join(campaigns_dir, "broken.json"), "w") as f:
            f.write("{not valid json")
        manager = CampaignManager(self.world, data_root=self.tmp_root)
        self.assertEqual(manager.definitions, {})


def _simple_definition(campaign_id="test_campaign", transitions=None, outcome="Victory"):
    return CampaignDefinition(
        campaign_id=campaign_id, name="Test Campaign", description="A test.",
        start_node_id="node_start",
        nodes={
            "node_start": CampaignNode(
                node_id="node_start", description="Start.", node_type="QUEST",
                quest_template_id="test_quest_template",
                transitions=transitions if transitions is not None else [
                    CampaignTransition(trigger="SUCCESS", target_node_id="node_end"),
                ],
            ),
            "node_end": CampaignNode(node_id="node_end", description="End.", node_type="END", outcome=outcome),
        },
    )


class TestStartCampaign(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.world.campaign_manager
        self.manager.definitions["test_campaign"] = _simple_definition()

    def test_unknown_campaign_returns_false(self):
        self.assertFalse(self.manager.start_campaign("totally_bogus_campaign_xyz", self.player))

    def test_already_active_returns_false(self):
        self.player.runtime_state.quests.active_campaigns["test_campaign"] = {}
        self.assertFalse(self.manager.start_campaign("test_campaign", self.player))

    def test_already_completed_returns_false(self):
        self.player.runtime_state.quests.completed_campaigns["test_campaign"] = {}
        self.assertFalse(self.manager.start_campaign("test_campaign", self.player))

    def test_missing_start_node_returns_false(self):
        broken_def = _simple_definition("broken_campaign")
        broken_def.start_node_id = "totally_bogus_node_xyz"
        self.manager.definitions["broken_campaign"] = broken_def
        self.assertFalse(self.manager.start_campaign("broken_campaign", self.player))

    def test_successful_start_triggers_first_node(self):
        with patch.object(self.world.quest_manager, "start_quest") as mock_start_quest:
            result = self.manager.start_campaign("test_campaign", self.player)
        self.assertTrue(result)
        mock_start_quest.assert_called_once()
        self.assertIn("test_campaign", self.player.runtime_state.quests.active_campaigns)


class TestHandleQuestCompletion(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.world.campaign_manager

    def test_unknown_campaign_returns_empty_string(self):
        result = self.manager.handle_quest_completion("totally_bogus_campaign_xyz", "node_start", "SUCCESS", self.player)
        self.assertEqual(result, "")

    def test_unknown_node_returns_empty_string(self):
        self.manager.definitions["test_campaign"] = _simple_definition()
        result = self.manager.handle_quest_completion("test_campaign", "totally_bogus_node_xyz", "SUCCESS", self.player)
        self.assertEqual(result, "")

    def test_missing_player_state_skips_history_but_still_advances(self):
        self.manager.definitions["test_campaign"] = _simple_definition()
        # No active_campaigns entry for this player -- player_state is falsy,
        # so history-recording is skipped, but the transition scan and node
        # trigger still proceed. Since there's no active_campaigns entry,
        # the END node's completion pop is also skipped (a separate branch,
        # covered by TestTriggerNode) -- so the finite_adventure status is
        # the only observable side effect here.
        result = self.manager.handle_quest_completion("test_campaign", "node_start", "SUCCESS", self.player)
        self.assertEqual(self.player.runtime_state.quests.finite_adventure["status"], "completed")

    def test_empty_transitions_falls_to_path_ends_here(self):
        self.manager.definitions["test_campaign"] = _simple_definition(transitions=[])
        self.player.runtime_state.quests.active_campaigns["test_campaign"] = {
            "current_node": "node_start", "history": [], "variables": {},
        }
        result = self.manager.handle_quest_completion("test_campaign", "node_start", "SUCCESS", self.player)
        self.assertEqual(result, "The campaign path ends here.")

    def test_failure_trigger_matches_a_failure_resolution(self):
        transitions = [CampaignTransition(trigger="FAILURE", target_node_id="node_end", narrative_text="You failed.")]
        self.manager.definitions["test_campaign"] = _simple_definition(transitions=transitions)
        self.player.runtime_state.quests.active_campaigns["test_campaign"] = {
            "current_node": "node_start", "history": [], "variables": {},
        }
        result = self.manager.handle_quest_completion("test_campaign", "node_start", "VIOLENT_FAILURE", self.player)
        self.assertEqual(result, "You failed.")

    def test_failed_rng_roll_skips_transition_and_ends_path(self):
        transitions = [CampaignTransition(trigger="SUCCESS", target_node_id="node_end", chance=0.0)]
        self.manager.definitions["test_campaign"] = _simple_definition(transitions=transitions)
        self.player.runtime_state.quests.active_campaigns["test_campaign"] = {
            "current_node": "node_start", "history": [], "variables": {},
        }
        with patch("engine.campaign.campaign_manager.random.random", return_value=1.0):
            result = self.manager.handle_quest_completion("test_campaign", "node_start", "SUCCESS", self.player)
        self.assertEqual(result, "The campaign path ends here.")

    def test_transition_to_nonexistent_node_falls_to_path_ends_here(self):
        transitions = [CampaignTransition(trigger="SUCCESS", target_node_id="totally_bogus_target_node_xyz")]
        self.manager.definitions["test_campaign"] = _simple_definition(transitions=transitions)
        self.player.runtime_state.quests.active_campaigns["test_campaign"] = {
            "current_node": "node_start", "history": [], "variables": {},
        }
        result = self.manager.handle_quest_completion("test_campaign", "node_start", "SUCCESS", self.player)
        self.assertEqual(result, "The campaign path ends here.")

    def test_advance_without_player_state_skips_current_node_update(self):
        self.manager.definitions["test_campaign"] = _simple_definition()
        # No active_campaigns entry -- exercises the advance path's own
        # "if player_state:" guard (separate from the earlier history one).
        result = self.manager.handle_quest_completion("test_campaign", "node_start", "SUCCESS", self.player)
        self.assertEqual(self.player.runtime_state.quests.finite_adventure["current_node"], "node_end")


class TestTriggerNode(GameTestBase):
    def test_non_quest_non_end_node_is_a_noop(self):
        manager = self.world.campaign_manager
        node = CampaignNode(node_id="cutscene_node", description="A cutscene.", node_type="CUTSCENE")
        manager._trigger_node("test_campaign", node, self.player)  # must not raise

    def test_end_node_without_active_campaign_state_skips_pop(self):
        manager = self.world.campaign_manager
        node = CampaignNode(node_id="node_end", description="End.", node_type="END", outcome="Victory")
        # No active_campaigns entry for "test_campaign".
        manager._trigger_node("test_campaign", node, self.player)
        self.assertNotIn("test_campaign", self.player.runtime_state.quests.completed_campaigns)
        self.assertEqual(self.player.runtime_state.quests.finite_adventure["status"], "completed")


if __name__ == "__main__":
    unittest.main()
