# tests/singles/test_key_matching.py
from typing import cast, Any
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container
from engine.items.key import Key

class TestKeyMatching(GameTestBase):

    def setUp(self):
        super().setUp()
        self.container = Container("chest", "Test Chest", locked=True)
        self.world.add_item_to_room("town", "town_square", self.container)

    def test_explicit_container_key_id(self):
        """Verify unlock when container specifies the required key ID."""
        self.container.properties["key_id"] = "skeleton_key"
        
        key = Key(obj_id="skeleton_key", name="Bone Key")
        self.player.inventory.add_item(key)
        
        msg = key.use(self.player, self.container)
        self.assertIn("You unlock", msg)
        self.assertFalse(self.container.properties["locked"])

    def test_explicit_key_target_id(self):
        """Verify unlock when key specifies the target container ID."""
        self.container.obj_id = "specific_chest"
        self.container.properties["key_id"] = None # Clear this to test the other direction
        
        key = Key(obj_id="random_key", name="Specific Key", target_id="specific_chest")
        self.player.inventory.add_item(key)
        
        msg = key.use(self.player, self.container)
        self.assertIn("You unlock", msg)
        self.assertFalse(self.container.properties["locked"])

    def test_name_fuzzy_match(self):
        """Verify unlock when no IDs match but key name is contained in container name."""
        self.container.name = "Iron Strongbox"
        self.container.properties["key_id"] = None
        
        # "Iron Key" should fit "Iron Strongbox" via fallback logic
        key = Key(obj_id="k1", name="Iron Key") 
        self.player.inventory.add_item(key)
        
        msg = key.use(self.player, self.container)
        self.assertIn("You unlock", msg)
        self.assertFalse(self.container.properties["locked"])