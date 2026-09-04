# tests/singles/test_quest_state_dialogue.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestQuestStateDialogue(GameTestBase):

    def setUp(self):
        super().setUp()
        self.km = self.game.knowledge_manager
        
        self.km.topics["quest_talk"] = {
            "display_name": "The Mission",
            "responses": [
                {
                    "text": "Please hurry!",
                    "conditions": { "quest_state": { "state": "active", "id_pattern": "my_quest" } },
                    "priority": 20
                },
                {
                    "text": "Thank you for your help.",
                    "conditions": { "quest_state": { "state": "completed", "id_pattern": "my_quest" } },
                    "priority": 20
                },
                {
                    "text": "I have a job for you.",
                    "conditions": {},
                    "priority": 0
                }
            ]
        }

    def test_dialogue_progression(self):
        """Verify responses change as quest progresses."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        
        # 1. Before Quest
        resp1 = self.km.get_response(npc, "quest_talk", self.player)
        self.assertIn("job for you", resp1)

        # 2. During Quest
        self.player.quest_log["my_quest_1"] = {"instance_id": "my_quest_1", "state": "active"}
        resp2 = self.km.get_response(npc, "quest_talk", self.player)
        self.assertIn("hurry", resp2)

        # 3. After Quest
        del self.player.quest_log["my_quest_1"]
        self.player.completed_quest_log["my_quest_1"] = {"state": "completed"}
        # Archived logs are also checked by KM usually? 
        # Logic in knowledge_manager.py checks completed_quest_log AND archived_quest_log.
        
        resp3 = self.km.get_response(npc, "quest_talk", self.player)
        self.assertIn("Thank you", resp3)