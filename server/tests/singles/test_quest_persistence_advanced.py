# tests/singles/test_quest_persistence_advanced.py
import os
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestQuestPersistenceAdvanced(GameTestBase):
    
    TEST_SAVE = "test_quest_adv.json"

    def tearDown(self):
        save_path = os.path.join("data", "saves", self.TEST_SAVE)
        if os.path.exists(save_path):
            os.remove(save_path)
        super().tearDown()

    def test_ready_quest_persistence(self):
        """Verify quests waiting for turn-in persist correctly."""
        # 1. Setup Ready Quest
        npc = NPCFactory.create_npc_from_template("village_elder", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        quest_id = "test_persist_01"
        self.player.runtime_state.quests.active[quest_id] = {
            "instance_id": quest_id,
            "state": "ready_to_complete",
            "giver_instance_id": npc.obj_id,
            "title": "Persistent Quest",
            "type": "kill",
            "objective": {}
        }
        
        # 2. Save and Load
        self.world.save_game(self.TEST_SAVE)
        self.player.runtime_state.quests.active = {} # Wipe
        self.world.load_save_game(self.TEST_SAVE)
        
        # 3. Assertions
        loaded_player = self.world.player
        self.assertIsNotNone(loaded_player)
        if loaded_player:
            self.assertIn(quest_id, loaded_player.runtime_state.quests.active)
            loaded_q = loaded_player.runtime_state.quests.active[quest_id]
            self.assertEqual(loaded_q["state"], "ready_to_complete")
            self.assertEqual(loaded_q["giver_instance_id"], npc.obj_id)
