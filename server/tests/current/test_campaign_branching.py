# tests/current/test_campaign_branching.py
from typing import Dict, Any
from tests.fixtures import GameTestBase
from engine.campaign.campaign_models import CampaignDefinition, CampaignNode, CampaignTransition
from engine.npcs.npc_factory import NPCFactory

class TestCampaignBranching(GameTestBase):
    """
    Verifies that the CampaignManager correctly navigates the narrative graph
    based on quest outcomes (Resolutions).
    """

    def setUp(self):
        super().setUp()
        self.cm = self.world.campaign_manager
        self.qm = self.world.quest_manager
        
        # 1. Setup Dummy Quest Templates
        self.qm.quest_templates["quest_intro"] = {
            "title": "Intro Quest", "type": "kill",
            "stages": [{"objective": {"type": "kill", "target_template_id": "rat", "required_quantity": 1}}]
        }
        self.qm.quest_templates["quest_war"] = {
            "title": "War Path", "type": "kill",
            "stages": [{"objective": {"type": "kill", "target_template_id": "boss", "required_quantity": 1}}]
        }
        self.qm.quest_templates["quest_peace"] = {
            "title": "Peace Path", "type": "talk",
            "stages": [{"objective": {"type": "talk", "target_npc_id": "boss"}}]
        }
        
        # 2. Construct Campaign Definition (The Flowchart)
        # Node 1: Intro -> Branch
        node_intro = CampaignNode(
            node_id="node_1",
            description="Start",
            quest_template_id="quest_intro",
            transitions=[
                CampaignTransition(trigger="VIOLENT_SUCCESS", target_node_id="node_war", narrative_text="You chose violence."),
                CampaignTransition(trigger="PEACEFUL_SUCCESS", target_node_id="node_peace", narrative_text="You chose peace.")
            ]
        )
        
        # Node 2A: War
        node_war = CampaignNode(
            node_id="node_war", description="War", quest_template_id="quest_war",
            transitions=[CampaignTransition(trigger="SUCCESS", target_node_id="node_end_bad")]
        )
        
        # Node 2B: Peace
        node_peace = CampaignNode(
            node_id="node_peace", description="Peace", quest_template_id="quest_peace",
            transitions=[CampaignTransition(trigger="SUCCESS", target_node_id="node_end_good")]
        )
        
        # End Nodes
        node_end_good = CampaignNode(node_id="node_end_good", node_type="END", description="Good End", outcome="ALLIANCE")
        node_end_bad = CampaignNode(node_id="node_end_bad", node_type="END", description="Bad End", outcome="DESTRUCTION")
        
        self.campaign_def = CampaignDefinition(
            campaign_id="test_branching",
            name="Branching Test",
            description="A test of logic.",
            start_node_id="node_1",
            nodes={
                "node_1": node_intro,
                "node_war": node_war,
                "node_peace": node_peace,
                "node_end_good": node_end_good,
                "node_end_bad": node_end_bad
            }
        )
        
        # Inject into Manager
        self.cm.definitions["test_branching"] = self.campaign_def

    def test_campaign_violent_path(self):
        """Verify returning VIOLENT_SUCCESS triggers the War node."""
        # 1. Start Campaign
        self.cm.start_campaign("test_branching", self.player)
        
        # Check Quest Log has Intro
        intro_instance = next((k for k in self.player.runtime_state.quests.active if k.startswith("quest_intro")), None)
        self.assertIsNotNone(intro_instance)
        
        if not intro_instance: return # Type guard for Pylance

        # 2. Complete with VIOLENCE
        # We simulate the QuestManager calling back to CampaignManager
        msg = self.qm.complete_quest(self.player, intro_instance, resolution="VIOLENT_SUCCESS")
        
        # 3. Assert Transitions
        self.assertIn("You chose violence", msg)
        
        # Check active quest is now War
        war_instance = next((k for k in self.player.runtime_state.quests.active if k.startswith("quest_war")), None)
        self.assertIsNotNone(war_instance, "War quest should have started.")
        self.assertIsNone(self.player.runtime_state.quests.active.get(intro_instance), "Intro quest should be gone.")
        
        # Check Player State
        state = self.player.runtime_state.quests.active_campaigns["test_branching"]
        self.assertEqual(state["current_node"], "node_war")

    def test_campaign_peaceful_path(self):
        """Verify returning PEACEFUL_SUCCESS triggers the Peace node."""
        self.cm.start_campaign("test_branching", self.player)
        intro_instance = next((k for k in self.player.runtime_state.quests.active if k.startswith("quest_intro")), None)
        
        self.assertIsNotNone(intro_instance)
        if not intro_instance: return # Type guard

        # Complete with PEACE
        msg = self.qm.complete_quest(self.player, intro_instance, resolution="PEACEFUL_SUCCESS")
        
        self.assertIn("You chose peace", msg)
        
        # Check active quest is Peace
        peace_instance = next((k for k in self.player.runtime_state.quests.active if k.startswith("quest_peace")), None)
        self.assertIsNotNone(peace_instance, "Peace quest should have started.")
        
        state = self.player.runtime_state.quests.active_campaigns["test_branching"]
        self.assertEqual(state["current_node"], "node_peace")

    def test_campaign_completion(self):
        """Verify reaching an END node closes the campaign."""
        # Fast forward to Peace Node
        self.player.runtime_state.quests.active_campaigns["test_branching"] = {
            "current_node": "node_peace",
            "history": [], "variables": {}
        }
        # Start the quest associated with this node manually to set up state
        self.qm.start_quest("quest_peace", self.player, campaign_context={"campaign_id": "test_branching", "node_id": "node_peace"})
        
        peace_instance = next((k for k in self.player.runtime_state.quests.active if k.startswith("quest_peace")), None)
        self.assertIsNotNone(peace_instance)
        if not peace_instance: return # Type guard

        # Complete it
        self.qm.complete_quest(self.player, peace_instance, resolution="SUCCESS")
        
        # Assert Campaign is removed from active list (End State)
        self.assertNotIn("test_branching", self.player.runtime_state.quests.active_campaigns)
