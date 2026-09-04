# tests/singles/test_dynamic_region_persistence_deep.py
import os
from tests.fixtures import GameTestBase
from engine.world.region_generator import RegionGenerator
from engine.items.item_factory import ItemFactory

class TestDynamicRegionPersistenceDeep(GameTestBase):
    
    TEST_SAVE = "test_dyn_deep.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_dynamic_region_items_persist(self):
        """Verify dropped items inside a procedurally generated region persist."""
        # 1. Generate Region
        gen = RegionGenerator(self.world)
        result = gen.generate_region("caves", 5)
        if not result: return
        region, entry_id = result
        self.world.add_region(region.obj_id, region)
        
        # 2. Go there
        self.player.current_region_id = region.obj_id
        self.player.current_room_id = entry_id
        self.world.current_region_id = region.obj_id
        self.world.current_room_id = entry_id
        
        # 3. Drop Item
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword, "Failed to create sword.")
        
        if sword:
            self.player.inventory.add_item(sword)
            self.game.process_command("drop iron sword")
            
            # Verify drop worked BEFORE saving
            current_items = self.world.get_items_in_current_room()
            self.assertTrue(any(i.name == "iron sword" for i in current_items), "Setup failed: Sword was not dropped in room.")
            
        # 4. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 5. Load
        self.world.load_save_game(self.TEST_SAVE)
        
        # 6. Verify Item Exists After Load
        # Get items from the loaded world state
        room_items = self.world.get_items_in_current_room()
        found = any(i.name == "iron sword" for i in room_items)
        self.assertTrue(found, "Item dropped in generated region must exist after load.")