# tests/singles/test_persistence_extended.py
import os
from tests.fixtures import GameTestBase

class TestPersistenceExtended(GameTestBase):
    
    TEST_SAVE = "test_skills_save.json"

    def tearDown(self):
        # Cleanup
        if os.path.exists(os.path.join(self.world.save_directory, self.TEST_SAVE)):
            try:
                os.remove(os.path.join(self.world.save_directory, self.TEST_SAVE))
            except:
                pass
        super().tearDown()

    def test_skills_save_load(self):
        """Verify skill levels and XP persist through save/load cycle."""
        # 1. Setup Player Skills
        self.player.add_skill("crafting", 5)
        self.player.runtime_state.progression.skills["crafting"]["xp"] = 50
        
        self.player.add_skill("lockpicking", 2)
        
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Wipe State
        self.player.runtime_state.progression.skills = {}
        
        # 4. Load
        self.world.load_save_game(self.TEST_SAVE)
        
        # 5. Verify
        # Note: self.player might be a new object reference after load, 
        # but self.world.player is updated.
        loaded_player = self.world.player
        self.assertIsNotNone(loaded_player)
        
        if loaded_player:
            # Check Crafting
            self.assertIn("crafting", loaded_player.runtime_state.progression.skills)
            crafting = loaded_player.runtime_state.progression.skills["crafting"]
            self.assertEqual(crafting["level"], 5)
            self.assertEqual(crafting["xp"], 50)
            
            # Check Lockpicking
            self.assertIn("lockpicking", loaded_player.runtime_state.progression.skills)
            self.assertEqual(loaded_player.runtime_state.progression.skills["lockpicking"]["level"], 2)
