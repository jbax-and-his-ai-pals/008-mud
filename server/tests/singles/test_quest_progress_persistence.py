# tests/singles/test_quest_progress_persistence.py
import os
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestQuestProgressPersistence(GameTestBase):
    
    TEST_SAVE = "test_quest_prog.json"

    def tearDown(self):
        if os.path.exists(os.path.join(self.world.save_directory, self.TEST_SAVE)):
            try: os.remove(os.path.join(self.world.save_directory, self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_kill_count_saves(self):
        """Verify quest objective progress (kill counts) persists."""
        # 1. Setup Quest
        quest_id = "rat_killer"
        target_tid = "giant_rat"
        
        self.player.runtime_state.quests.active[quest_id] = {
            "instance_id": quest_id,
            "type": "kill",
            "state": "active",
            "title": "Rat Hunt",
            "current_stage_index": 0,
            "stages": [
                {
                    "stage_index": 0,
                    "objective": {
                        "type": "kill",
                        "target_template_id": target_tid,
                        "required_quantity": 5,
                        "current_quantity": 0
                    }
                }
            ]
        }
        
        # 2. Make Progress (Kill 2 rats)
        rat = NPCFactory.create_npc_from_template(target_tid, self.world)
        if rat:
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": rat})
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": rat})
            
        self.assertEqual(self.player.runtime_state.quests.active[quest_id]["stages"][0]["objective"]["current_quantity"], 2)
        
        # 3. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 4. Wipe State
        self.player.runtime_state.quests.active = {}
        
        # 5. Load
        self.world.load_save_game(self.TEST_SAVE)
        loaded = self.world.player
        
        # 6. Verify
        self.assertIsNotNone(loaded)
        if loaded:
            self.assertIn(quest_id, loaded.runtime_state.quests.active)
            q = loaded.runtime_state.quests.active[quest_id]
            # Access via stages
            self.assertEqual(q["stages"][0]["objective"]["current_quantity"], 2)
