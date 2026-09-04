# tests_quarantine/test_nested_container_persistence.py
# import os
# from typing import cast
# from tests.fixtures import GameTestBase
# from engine.items.item_factory import ItemFactory
# from engine.items.container import Container

# class TestNestedContainerPersistence(GameTestBase):
    
#     TEST_SAVE = "test_nesting.json"

#     def setUp(self):
#         super().setUp()
#         # Override the template to ensure it is a Container, as default might be Junk
#         self.world.item_templates["item_empty_crate"] = {
#             "type": "Container", 
#             "name": "Crate", 
#             "value": 10, 
#             "weight": 5.0,
#             "properties": {"capacity": 100.0, "is_open": True, "contains": []}
#         }
#         self.world.item_templates["item_ruby"] = {
#             "type": "Gem", 
#             "name": "Ruby", 
#             "value": 100, 
#             "weight": 0.1
#         }

#     def tearDown(self):
#         path = os.path.join("data", "saves", self.TEST_SAVE)
#         if os.path.exists(path):
#             try: os.remove(path)
#             except: pass
#         super().tearDown()

#     def test_nested_structure(self):
#         """Verify Item C inside Bag B inside Chest A persists."""
#         # 1. Setup
#         chest = ItemFactory.create_item_from_template("item_empty_crate", self.world)
#         bag = ItemFactory.create_item_from_template("item_empty_crate", self.world) # Using crate template as generic container
#         gem = ItemFactory.create_item_from_template("item_ruby", self.world)
        
#         if not (chest and bag and gem): 
#             self.fail("Failed to create test items")
        
#         # Cast
#         if not isinstance(chest, Container) or not isinstance(bag, Container):
#             self.fail("Created items are not Containers")
#             return

#         chest.name = "Big Chest"; chest.properties["is_open"] = True
#         bag.name = "Small Bag"; bag.properties["is_open"] = True
        
#         # 2. Nest: Gem -> Bag -> Chest -> Inventory
#         bag.add_item(gem)
#         chest.add_item(bag)
#         self.player.inventory.add_item(chest)
        
#         # 3. Save
#         self.world.save_game(self.TEST_SAVE)
        
#         # 4. Wipe
#         self.player.inventory.slots = []
        
#         # 5. Load
#         self.world.load_save_game(self.TEST_SAVE)
#         loaded = self.world.player
        
#         # 6. Verify Hierarchy
#         if loaded:
#             # Find Chest
#             loaded_chest = loaded.inventory.find_item_by_name("Big Chest")
#             self.assertIsInstance(loaded_chest, Container)
#             loaded_chest = cast(Container, loaded_chest)
            
#             # Find Bag inside Chest
#             loaded_bag = loaded_chest.find_item_by_name("Small Bag")
#             self.assertIsInstance(loaded_bag, Container)
#             loaded_bag = cast(Container, loaded_bag)
            
#             # Find Gem inside Bag
#             loaded_gem = loaded_bag.find_item_by_name("Ruby")
#             self.assertIsNotNone(loaded_gem)
#             if loaded_gem:
#                 self.assertEqual(loaded_gem.name, "Ruby")