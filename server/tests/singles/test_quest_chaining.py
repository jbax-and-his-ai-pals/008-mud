# tests/singles/test_quest_chaining.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestQuestChaining(GameTestBase):

    def setUp(self):
        super().setUp()
        self.km = self.game.knowledge_manager
        
        # Define chained topic
        # Only available if 'intro_quest' is completed
        self.km.topics["main_quest_start"] = {
            "display_name": "The Real Threat",
            "responses": [
                {
                    "text": "Now that you've handled the rats, we can discuss the dragon.",
                    "conditions": { "quest_state": { "state": "completed", "id_pattern": "intro_quest" } },
                    "priority": 10
                },
                {
                    "text": "I can't trust you yet. Help with the rats first.",
                    "conditions": {},
                    "priority": 0
                }
            ]
        }

    def test_prerequisite_logic(self):
        """Verify 'The Real Threat' dialogue changes based on 'intro_quest' state."""
        npc = NPCFactory.create_npc_from_template("village_elder", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        # 1. Check before prerequisite
        response_early = self.km.get_response(npc, "main_quest_start", self.player)
        self.assertIn("Help with the rats", response_early)
        
        # 2. Complete Prerequisite
        self.player.runtime_state.quests.completed["intro_quest_01"] = {
            "instance_id": "intro_quest_01",
            "state": "completed",
            "giver_instance_id": npc.obj_id
        }
        
        # 3. Check after prerequisite
        response_later = self.km.get_response(npc, "main_quest_start", self.player)
        self.assertIn("discuss the dragon", response_later)
