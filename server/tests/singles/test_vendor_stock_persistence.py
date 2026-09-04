# tests/singles/test_vendor_stock_persistence.py
import os
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestVendorStockPersistence(GameTestBase):
    
    TEST_SAVE = "test_vendor_stock.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_limited_stock_depletion(self):
        """Verify that if a vendor has inventory updates, they persist."""
        merchant = NPCFactory.create_npc_from_template("merchant", self.world, instance_id="persisting_merchant")
        self.assertIsNotNone(merchant, "Failed to create merchant.")
        
        if not merchant: return
        
        self.world.add_npc(merchant)
        
        # 1. Player sells unique item to merchant
        self.world.item_templates["unique_relic"] = {"type": "Treasure", "name": "Relic", "value": 100}
        
        relic = ItemFactory.create_item_from_template("unique_relic", self.world)
        if relic:
            # Simulate sold item ending up in NPC inventory
            merchant.inventory.add_item(relic)
            
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Load
        self.world.load_save_game(self.TEST_SAVE)
        loaded_merchant = self.world.get_npc("persisting_merchant")
        
        # 4. Assert
        self.assertIsNotNone(loaded_merchant)
        if loaded_merchant:
            self.assertEqual(loaded_merchant.inventory.count_item("unique_relic"), 1, 
                             "NPC inventory should persist across saves.")