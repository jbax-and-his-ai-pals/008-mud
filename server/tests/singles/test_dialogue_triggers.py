# tests/singles/test_dialogue_triggers.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestDialogueTriggers(GameTestBase):

    def setUp(self):
        super().setUp()
        self.km = self.game.knowledge_manager
        
        # Define a topic with conditional responses
        self.km.topics["secret"] = {
            "display_name": "Secret",
            "responses": [
                {
                    "text": "I trust you with the secret key.",
                    "conditions": { "quest_state": { "state": "completed", "id_pattern": "trust_quest" } },
                    "priority": 10
                },
                {
                    "text": "I don't know you well enough.",
                    "conditions": {},
                    "priority": 0
                }
            ]
        }

    def test_conditional_response_quest_state(self):
        """Verify NPC gives different info based on quest completion."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)

        # 1. Default State
        response_default = self.km.get_response(npc, "secret", self.player)
        self.assertIn("don't know you", response_default)

        # 2. Complete Quest
        self.player.completed_quest_log["trust_quest_01"] = {
            "instance_id": "trust_quest_01",
            "state": "completed",
            "giver_instance_id": npc.obj_id
        }

        # 3. Authenticated State
        response_trusted = self.km.get_response(npc, "secret", self.player)
        self.assertIn("trust you", response_trusted)