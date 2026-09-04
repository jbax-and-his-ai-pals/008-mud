# tests/singles/test_knowledge_logic.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestKnowledgeLogic(GameTestBase):
    
    def setUp(self):
        super().setUp()
        self.km = self.game.knowledge_manager
        
        # Inject a conditional topic
        self.km.topics["secret_topic"] = {
            "display_name": "The Secret",
            "responses": [
                {
                    "text": "I trust you now. The treasure is in the well.",
                    "conditions": { "quest_state": { "state": "completed", "id_pattern": "test_quest" } },
                    "priority": 20
                },
                {
                    "text": "I don't know you well enough.",
                    "conditions": {},
                    "priority": 0
                }
            ]
        }

    def test_conditional_response(self):
        """Verify NPCs give different answers based on quest state."""
        # Ensure a 'villager' template exists
        if "villager" not in self.world.npc_templates:
            self.world.npc_templates["villager"] = {
                "name": "Villager", "description": "Normal.", "faction": "neutral"
            }

        npc = NPCFactory.create_npc_from_template("villager", self.world)
        self.assertIsNotNone(npc, "Failed to create test NPC.")
        
        if npc:
            self.world.add_npc(npc)
            
            # 1. Default State (Quest not done)
            response_1 = self.km.get_response(npc, "secret_topic", self.player)
            self.assertIn("don't know you", response_1)
            
            # 2. Complete Quest
            self.player.runtime_state.quests.completed["test_quest_01"] = {
                "state": "completed",
                "giver_instance_id": npc.obj_id
            }
            
            # 3. New State
            response_2 = self.km.get_response(npc, "secret_topic", self.player)
            self.assertIn("treasure is in the well", response_2)
