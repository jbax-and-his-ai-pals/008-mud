# tests/singles/test_save_inventory_state.py
import os
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestSaveInventoryState(GameTestBase):
    
    TEST_SAVE = "test_inv_state.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_inventory_data_persistence(self):
        """Verify inventory items and quantities persist."""
        # 1. Setup Inventory
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        
        if potion and sword:
            self.player.inventory.add_item(potion, 5) # Stack
            self.player.inventory.add_item(sword) # Single
            
            # 2. Save
            self.world.save_game(self.TEST_SAVE)
            
            # 3. Clear
            self.player.inventory.slots = []
            
            # 4. Load
            self.world.load_save_game(self.TEST_SAVE)
            
            # 5. Assert
            loaded_player = self.world.player
            self.assertIsNotNone(loaded_player)
            if loaded_player:
                self.assertEqual(loaded_player.inventory.count_item("item_healing_potion_small"), 5)
                self.assertEqual(loaded_player.inventory.count_item("item_iron_sword"), 1)