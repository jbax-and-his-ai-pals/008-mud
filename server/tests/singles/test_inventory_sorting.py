# tests/singles/test_inventory_sorting.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestInventorySorting(GameTestBase):
    def test_sorting_order(self):
        """Verify items are sorted by type/name in output."""
        # Create items out of order
        i1 = ItemFactory.create_item_from_template("item_iron_sword", self.world) # Weapon
        i2 = ItemFactory.create_item_from_template("item_healing_potion_small", self.world) # Consumable
        i3 = ItemFactory.create_item_from_template("item_leather_cap", self.world) # Armor
        
        if i1 and i2 and i3:
            self.player.inventory.add_item(i1)
            self.player.inventory.add_item(i2)
            self.player.inventory.add_item(i3)
            
            # Act
            output = self.player.inventory.list_items()
            
            # Assert
            # Sort key is (ClassName, Name).
            # Armor (A) < Consumable (C) < Weapon (W)
            # Expected order: Leather Cap, Small Healing Potion, Iron Sword
            
            pos_cap = output.lower().find("leather cap")
            pos_pot = output.lower().find("small healing potion")
            pos_sword = output.lower().find("iron sword")
            
            self.assertNotEqual(pos_cap, -1)
            self.assertNotEqual(pos_pot, -1)
            self.assertNotEqual(pos_sword, -1)
            
            self.assertLess(pos_cap, pos_pot, "Armor should come before Consumable")
            self.assertLess(pos_pot, pos_sword, "Consumable should come before Weapon")