# tests/singles/test_world_item_persistence.py
import os
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestWorldItemPersistence(GameTestBase):
    
    TEST_SAVE = "test_item_persist.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try:
                os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except:
                pass
        super().tearDown()

    def test_dropped_items_persist(self):
        """Verify items dropped in a room exist after loading."""
        # 1. Create item
        # We use a standard template. 
        unique_item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(unique_item)
        if not unique_item: return

        # Mark it with a unique property. Properties ARE persisted.
        # Renaming via .name attribute is NOT persisted by default serializer logic currently.
        unique_item.properties["test_marker_id"] = 99999
        
        # 2. Drop it in current room
        rid = self.player.current_region_id
        room_id = self.player.current_room_id
        if rid and room_id:
            self.world.add_item_to_room(rid, room_id, unique_item)
            
            # 3. Save
            self.world.save_game(self.TEST_SAVE)
            
            # 4. Clear World (Simulate restart)
            room = self.world.get_current_room()
            if room:
                room.items = [] # Wipe items
            
            # Verify gone
            items_in_room = self.world.get_items_in_current_room()
            self.assertEqual(len(items_in_room), 0)

            # 5. Load
            self.world.load_save_game(self.TEST_SAVE)
            
            # 6. Verify Persistence
            # Look for item with our specific marker property
            loaded_items = self.world.get_items_in_current_room()
            found_item = None
            for item in loaded_items:
                if item.properties.get("test_marker_id") == 99999:
                    found_item = item
                    break
            
            self.assertIsNotNone(found_item, "Item with unique property should exist after load.")
            if found_item:
                self.assertEqual(found_item.obj_id, "item_iron_sword")