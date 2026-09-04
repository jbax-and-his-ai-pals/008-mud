# tests/singles/test_equipment_effects.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestEquipmentEffects(GameTestBase):

    def test_equip_stat_modification(self):
        """Verify items with equip_effect modify effective stats."""
        # 1. Setup item with effect
        self.world.item_templates["ring_intel"] = {
            "type": "Armor", "name": "Sage Ring", "value": 100,
            "properties": {
                "equip_slot": ["neck"],
                "equip_effect": {
                    "type": "stat_mod",
                    "name": "Sage Wisdom",
                    "modifiers": {"intelligence": 5}
                }
            }
        }
        ring = ItemFactory.create_item_from_template("ring_intel", self.world)
        self.assertIsNotNone(ring)
        if not ring: return

        base_int = self.player.get_effective_stat("intelligence")
        self.player.inventory.add_item(ring)
        
        # 2. Equip
        self.player.equip_item(ring)
        
        # 3. Verify Boost
        self.assertEqual(self.player.get_effective_stat("intelligence"), base_int + 5)
        self.assertTrue(self.player.has_effect("Sage Wisdom"))
        
        # 4. Unequip
        self.player.unequip_item("neck")
        
        # 5. Verify Revert
        self.assertEqual(self.player.get_effective_stat("intelligence"), base_int)
        self.assertFalse(self.player.has_effect("Sage Wisdom"))