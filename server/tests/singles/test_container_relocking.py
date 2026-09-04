# tests/singles/test_container_relocking.py
from typing import cast, Any
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container
from engine.items.key import Key

class TestContainerRelocking(GameTestBase):

    def test_key_toggles_lock(self):
        """Verify using a key on an unlocked container locks it."""
        # 1. Setup Container (Unlocked, Closed)
        self.world.item_templates["chest"] = {
            "type": "Container", "name": "Chest", 
            "properties": { "locked": False, "is_open": False, "key_id": "k1" }
        }
        item_chest = ItemFactory.create_item_from_template("chest", self.world)
        
        if isinstance(item_chest, Container) and self.player:
            chest = cast(Container, item_chest)
            self.player.inventory.add_item(chest) # For ease of access
            
            # 2. Setup Key
            key = Key(obj_id="k1", name="Iron Key")
            self.player.inventory.add_item(key)
            
            # 3. Lock it
            msg = key.use(self.player, chest)
            self.assertIn("You lock", msg)
            self.assertTrue(chest.properties["locked"])
            
            # 4. Try Open (Should fail)
            msg_open = chest.open()
            self.assertIn("locked", msg_open)
            self.assertFalse(chest.properties["is_open"])
            
            # 5. Unlock it
            msg_unlock = key.use(self.player, chest)
            self.assertIn("You unlock", msg_unlock)
            self.assertFalse(chest.properties["locked"])