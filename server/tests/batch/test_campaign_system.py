# tests/batch/test_campaign_system.py
import time
import os
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.campaign.campaign_models import CampaignDefinition, CampaignNode, CampaignTransition

class TestCampaignSystem(GameTestBase):
    """
    Tests for the high-level Campaign system (Quest Chains) using the Node-based architecture.
    """

    def setUp(self):
        super().setUp()
        qm = self.world.quest_manager
        cm = self.world.campaign_manager
        
        # 1. Define Quest Templates
        qm.quest_templates["campaign_q1"] = {
            "title": "Part 1",
            "type": "fetch",
            "stages": [{
                "stage_index": 0,
                "description": "Get a rock.",
                "objective": {"type": "fetch", "item_id": "rock", "required_quantity": 1},
                "turn_in_id": "quest_giver"
            }],
            "rewards": {"xp": 100}
        }
        
        qm.quest_templates["campaign_q2"] = {
            "title": "Part 2",
            "type": "kill",
            "stages": [{
                "stage_index": 0,
                "description": "Kill a rat.",
                "objective": {"type": "kill", "target_template_id": "rat", "required_quantity": 1, "current_quantity": 0},
                "turn_in_id": "quest_giver"
            }],
            "rewards": {"gold": 50}
        }
        
        # 2. Define Campaign using Nodes (replacing the old list format)
        node_q1 = CampaignNode(
            node_id="node_q1",
            description="Start",
            quest_template_id="campaign_q1",
            transitions=[
                CampaignTransition(trigger="SUCCESS", target_node_id="node_q2")
            ]
        )
        
        node_q2 = CampaignNode(
            node_id="node_q2",
            description="Middle",
            quest_template_id="campaign_q2",
            transitions=[
                CampaignTransition(trigger="SUCCESS", target_node_id="node_end")
            ]
        )
        
        node_end = CampaignNode(
            node_id="node_end",
            node_type="END",
            description="Finished",
            outcome="VICTORY"
        )
        
        campaign_def = CampaignDefinition(
            campaign_id="test_campaign",
            name="The Test Saga",
            description="A test chain.",
            start_node_id="node_q1",
            nodes={
                "node_q1": node_q1,
                "node_q2": node_q2,
                "node_end": node_end
            }
        )
        
        cm.definitions["test_campaign"] = campaign_def
        
        # 3. Setup World Items/NPCs
        self.world.item_templates["rock"] = {"type": "Item", "name": "Rock"}
        self.world.npc_templates["rat"] = {"name": "Rat", "faction": "hostile", "level": 1, "health": 10}
        
        if "villager" not in self.world.npc_templates:
             self.world.npc_templates["villager"] = {"name": "Villager", "faction": "friendly"}

        self.giver = NPCFactory.create_npc_from_template("villager", self.world, instance_id="quest_giver")
        if self.giver:
            self.giver.current_region_id = self.player.current_region_id
            self.giver.current_room_id = self.player.current_room_id
            self.world.add_npc(self.giver)

    def test_campaign_start(self):
        """Verify starting a campaign adds the first quest to the log."""
        qm = self.world.quest_manager
        
        success = qm.start_campaign("test_campaign", self.player)
        self.assertTrue(success)
        
        # Check active campaigns
        self.assertIn("test_campaign", self.player.runtime_state.quests.active_campaigns)
        # Verify current node ID, not index
        self.assertEqual(self.player.runtime_state.quests.active_campaigns["test_campaign"]["current_node"], "node_q1")
        
        # Check Quest Log for Q1
        has_q1 = any(qid.startswith("campaign_q1") for qid in self.player.runtime_state.quests.active)
        self.assertTrue(has_q1, "First quest of campaign should be active.")

    def test_campaign_auto_advance(self):
        """Verify completing Q1 automatically starts Q2."""
        qm = self.world.quest_manager
        qm.start_campaign("test_campaign", self.player)
        
        self.assertIsNotNone(self.giver, "Quest giver NPC failed to create.")
        
        # Find the active instance ID for Q1
        q1_instance_id = next((qid for qid in self.player.runtime_state.quests.active if qid.startswith("campaign_q1")), None)
        self.assertIsNotNone(q1_instance_id, "Quest 1 not found in log.")
        
        # Fulfill Q1 (Fetch Rock)
        rock = ItemFactory.create_item_from_template("rock", self.world)
        self.assertIsNotNone(rock, "Failed to create rock item.")
        
        if rock: 
            self.player.inventory.add_item(rock)
        
        # Turn In
        if self.giver:
            res = self.game.process_command(f"talk {self.giver.name} complete")
        
        # Assertions
        self.assertIsNotNone(res, "Command result was None.")
        if res:
            self.assertIn("Quest Complete", res)
            # Depending on implementation details, transition text might or might not appear in talk output
            # but we can verify state change.
        
        # Verify Q1 moved to completed
        self.assertIn(q1_instance_id, self.player.runtime_state.quests.completed)
        
        # Verify Q2 started
        has_q2 = any(qid.startswith("campaign_q2") for qid in self.player.runtime_state.quests.active)
        self.assertTrue(has_q2, "Second quest should have started automatically.")
        
        # Verify Campaign Progress Node
        self.assertEqual(self.player.runtime_state.quests.active_campaigns["test_campaign"]["current_node"], "node_q2")

    def test_campaign_persistence(self):
        """Verify campaign progress saves and loads."""
        TEST_SAVE = "campaign_save.json"
        
        # 1. Manually set state to Node 2
        self.player.runtime_state.quests.active_campaigns["test_campaign"] = {
            "current_node": "node_q2",
            "history": [{"node_id": "node_q1", "resolution": "SUCCESS"}],
            "variables": {}
        }
        
        # 2. Save
        self.world.save_game(TEST_SAVE)
        
        # 3. Clear
        self.player.runtime_state.quests.active_campaigns = {}
        
        # 4. Load
        self.world.load_save_game(TEST_SAVE)
        
        # 5. Assert
        loaded = self.world.player
        self.assertIsNotNone(loaded)
        if loaded:
            state = loaded.runtime_state.quests.active_campaigns.get("test_campaign")
            self.assertIsNotNone(state)
            if state:
                self.assertEqual(state["current_node"], "node_q2")

        if os.path.exists(os.path.join("data", "saves", TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", TEST_SAVE))
            except: pass
