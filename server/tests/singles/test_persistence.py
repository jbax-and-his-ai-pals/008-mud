# tests/singles/test_persistence.py
import os
import stat
import time
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestPersistence(GameTestBase):
    
    TEST_SAVE_FILE = "unittest_save.json"

    def tearDown(self):
        # Cleanup the file created
        save_path = os.path.join("data", "saves", self.TEST_SAVE_FILE)
        if os.path.exists(save_path):
            for _ in range(3):
                try:
                    os.chmod(save_path, stat.S_IWRITE)
                    os.remove(save_path)
                    break
                except PermissionError:
                    time.sleep(0.1)
        super().tearDown()

    def test_save_load_roundtrip(self):
        """Verify saving and loading preserves player state."""
        # 1. Modify State
        # self.player is cast in fixtures, so this is safe
        self.player.runtime_state.gold = 999
        self.player.health = 50
        
        # Add a specific item
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword: self.player.inventory.add_item(sword)

        # 2. Save
        success = self.world.save_game(self.TEST_SAVE_FILE)
        self.assertTrue(success, "Save failed")

        # 3. Corrupt/Clear Current State (simulate restart)
        self.player.runtime_state.gold = 0
        self.player.inventory.slots = [] # Wipe inventory
        
        # 4. Load
        loaded, _, _ = self.world.load_save_game(self.TEST_SAVE_FILE)
        self.assertTrue(loaded, "Load failed")

        # 5. Assert State Restored
        # self.world.player is Optional[Player], so we must check it for Pylance
        loaded_player = self.world.player 
        
        self.assertIsNotNone(loaded_player, "Player object is None after load")
        
        # This 'if' block tells Pylance that loaded_player is definitely not None inside
        if loaded_player:
            self.assertEqual(loaded_player.runtime_state.gold, 999)
            self.assertEqual(loaded_player.health, 50)
            self.assertEqual(loaded_player.inventory.count_item("item_iron_sword"), 1)

    def test_load_invalid_location_resets_loaded_player_respawn(self):
        """Verify load recovery corrects the loaded player's location directly."""
        self.player.current_region_id = "missing_region"
        self.player.current_room_id = "missing_room"
        self.player.respawn_region_id = "town"
        self.player.respawn_room_id = "town_square"

        success = self.world.save_game(self.TEST_SAVE_FILE)
        self.assertTrue(success, "Save failed")

        loaded, _, _ = self.world.load_save_game(self.TEST_SAVE_FILE)
        self.assertTrue(loaded, "Load failed")
        self.assertIsNotNone(self.world.player)
        if self.world.player:
            self.assertEqual(("town", "town_square"), (self.world.player.current_region_id, self.world.player.current_room_id))
