# tests/singles/test_containers.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.key import Key
from engine.items.container import Container

class TestContainers(GameTestBase):

    def test_locked_container(self):
        """Verify a locked container cannot be opened without a key."""
        # 1. Setup: Ensure location is valid
        self.assertIsNotNone(self.player.current_region_id)
        self.assertIsNotNone(self.player.current_room_id)
        
        # Pylance needs these to be non-optional strings
        rid = self.player.current_region_id
        room_id = self.player.current_room_id

        if rid and room_id:
            # Create locked chest
            chest = ItemFactory.create_item_from_template("item_empty_crate", self.world)
            if isinstance(chest, Container):
                chest.name = "Locked Chest"
                chest.properties["locked"] = True
                chest.properties["key_id"] = "test_key_01"
                self.world.add_item_to_room(rid, room_id, chest)
                
                # 2. Try Open (Fail)
                msg_fail = self.game.process_command("open Locked Chest")
                self.assertIsNotNone(msg_fail)
                if msg_fail:
                    self.assertIn("locked", msg_fail)
                self.assertFalse(chest.properties["is_open"])
                
                # 3. Create Key
                key = Key(obj_id="test_key_01", name="Shiny Key", value=1)
                self.player.inventory.add_item(key)
                
                # 4. Use Key
                msg_unlock = self.game.process_command("use Shiny Key on Locked Chest")
                self.assertIsNotNone(msg_unlock)
                if msg_unlock:
                    self.assertIn("unlock", msg_unlock)
                self.assertFalse(chest.properties["locked"])
                
                # 5. Open (Success)
                msg_open = self.game.process_command("open Locked Chest")
                self.assertIsNotNone(msg_open)
                if msg_open:
                    self.assertIn("You open", msg_open)
                self.assertTrue(chest.properties["is_open"])

    def test_put_get_container(self):
        """Verify putting items in and taking them out of containers."""
        # 1. Setup: Location check
        self.assertIsNotNone(self.player.current_region_id)
        self.assertIsNotNone(self.player.current_room_id)
        
        rid = self.player.current_region_id
        room_id = self.player.current_room_id

        if rid and room_id:
            bag = ItemFactory.create_item_from_template("item_empty_crate", self.world)
            item = ItemFactory.create_item_from_template("item_iron_ingot", self.world)
            
            if isinstance(bag, Container) and item:
                bag.name = "Bag"
                bag.properties["is_open"] = True # Must be open to use
                self.world.add_item_to_room(rid, room_id, bag)
                self.player.inventory.add_item(item)
                
                # 2. Put Item in Bag
                self.game.process_command("put ingot in Bag")
                self.assertEqual(self.player.inventory.count_item("item_iron_ingot"), 0)
                self.assertEqual(len(bag.properties["contains"]), 1)
                
                # 3. Get Item from Bag
                self.game.process_command("get ingot from Bag")
                self.assertEqual(self.player.inventory.count_item("item_iron_ingot"), 1)
                self.assertEqual(len(bag.properties["contains"]), 0)