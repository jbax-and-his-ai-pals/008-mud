# tests/singles/test_instance_clearance.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestInstanceClearance(GameTestBase):

    def test_clear_region_objective_completion(self):
        """Verify 'clear_region' quests trigger completion when hostiles are gone."""
        # 1. Setup Quest in Log (Saga Structure)
        quest_id = "clear_test"
        objective_data = {
            "type": "clear_region",
            "target_template_id": "giant_rat"
        }
        
        self.player.runtime_state.quests.active[quest_id] = {
            "instance_id": quest_id,
            "type": "instance",
            "state": "active",
            "instance_region_id": "dynamic_cellar",
            "completion_check_enabled": True,
            "current_stage_index": 0,
            "objective": objective_data, # Sync top-level
            "stages": [
                {
                    "stage_index": 0,
                    "objective": objective_data
                }
            ]
        }
        
        # 2. Add Hostile to that dynamic region
        rat = NPCFactory.create_npc_from_template("giant_rat", self.world)
        if rat:
            rat.current_region_id = "dynamic_cellar"
            self.world.add_npc(rat)
            
            # 3. Check completion (should still be active)
            self.world.quest_manager.check_quest_completion()
            self.assertEqual(self.player.runtime_state.quests.active[quest_id]["state"], "active")
            
            # 4. Kill the rat
            rat.is_alive = False
            # Dispatch normally handles death cleanup but we manual check logic
            self.world.quest_manager.check_quest_completion()
            
            # 5. Assert: State should now be ready_to_complete
            self.assertEqual(self.player.runtime_state.quests.active[quest_id]["state"], "ready_to_complete")
