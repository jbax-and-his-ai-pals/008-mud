# tests/singles/test_quest_concurrency.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestQuestConcurrency(GameTestBase):

    def test_double_dipping_kills(self):
        """Verify killing one monster updates multiple active quests for that target."""
        # 1. Setup two identical quests
        q1_id = "kill_rats_guild"
        q2_id = "kill_rats_baker"
        
        target_template = "giant_rat"
        
        # Helper to create schema
        def make_quest(qid, title, qty):
            return {
                "instance_id": qid, "type": "kill", "state": "active",
                "title": title,
                "current_stage_index": 0,
                "stages": [
                    {
                        "stage_index": 0,
                        "objective": {"type": "kill", "target_template_id": target_template, "required_quantity": qty, "current_quantity": 0}
                    }
                ]
            }
        
        self.player.runtime_state.quests.active[q1_id] = make_quest(q1_id, "Guild Hunt", 5)
        self.player.runtime_state.quests.active[q2_id] = make_quest(q2_id, "Baker Hunt", 3)
        
        # 2. Create and Kill ONE rat
        rat = NPCFactory.create_npc_from_template(target_template, self.world)
        if rat:
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": rat})
            
            # 3. Assert BOTH updated
            # Note: Access via stages[0] because that's where the manager updates it now
            q1_obj = self.player.runtime_state.quests.active[q1_id]["stages"][0]["objective"]
            q2_obj = self.player.runtime_state.quests.active[q2_id]["stages"][0]["objective"]
            
            self.assertEqual(q1_obj["current_quantity"], 1, "First quest should update.")
            self.assertEqual(q2_obj["current_quantity"], 1, "Second quest should update from the same kill.")
