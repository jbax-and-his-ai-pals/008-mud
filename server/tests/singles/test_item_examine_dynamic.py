# tests/singles/test_item_examine_dynamic.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestItemExamineDynamic(GameTestBase):

    def test_examine_shows_durability(self):
        """Verify description updates when item is damaged."""
        # 1. Create Weapon
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if not sword: return
        
        # 2. Pristine Check
        desc_fresh = sword.examine()
        # Note: Depending on implementation, 'Durability' might explicitly show value
        # or be hidden if full. Checking for value or property presence.
        # Base Item.examine iterates properties.
        self.assertIn("Durability: 50", desc_fresh)
        
        # 3. Damage It
        sword.update_property("durability", 10)
        
        # 4. Damaged Check
        desc_damaged = sword.examine()
        self.assertIn("Durability: 10", desc_damaged)
        self.assertNotEqual(desc_fresh, desc_damaged)