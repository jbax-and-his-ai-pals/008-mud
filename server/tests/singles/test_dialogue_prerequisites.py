# tests/singles/test_dialogue_prerequisites.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestDialoguePrerequisites(GameTestBase):

    def test_chained_topic_unlock(self):
        """Verify a topic is only available after a specific condition is met."""
        km = self.game.knowledge_manager
        
        # Topic A: Available immediately
        km.topics["intro"] = {"display_name": "Intro", "responses": [{"text": "Hello"}]}
        
        # Topic B: Requires knowing "intro" (simulated via vocabulary check logic in a real app, 
        # but here we check quest state as a proxy for 'progress')
        km.topics["secret"] = {
            "display_name": "Secret",
            "responses": [
                {
                    "text": "The password is fish.",
                    "conditions": {"quest_state": {"state": "completed", "id_pattern": "tutorial"}},
                    "priority": 10
                },
                {
                    "text": "I can't tell you yet.",
                    "conditions": {},
                    "priority": 0
                }
            ]
        }
        
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        # 1. Ask before condition
        resp1 = km.get_response(npc, "secret", self.player)
        # FIX: Ensure response is not None before asserting (though get_response usually returns string)
        self.assertIsNotNone(resp1)
        if resp1:
            self.assertIn("can't tell you", resp1)
        
        # 2. Fulfill condition
        self.player.completed_quest_log["tutorial_01"] = {"state": "completed", "id": "tutorial_01"}
        
        # 3. Ask after condition
        resp2 = km.get_response(npc, "secret", self.player)
        self.assertIsNotNone(resp2)
        if resp2:
            self.assertIn("password is fish", resp2)