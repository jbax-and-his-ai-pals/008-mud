# tests/singles/test_equipment_stat_tracking.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
import time

class TestEquipmentStatStacking(GameTestBase):

    def test_mixed_stat_modifiers(self):
        """Verify positive and negative stats from different items sum correctly."""
        # 1. Setup Items
        self.world.item_templates["boots_speed"] = {
            "type": "Armor", "name": "Boots of Speed", "value": 1,
            "properties": {
                "equip_slot": ["feet"],
                "equip_effect": {
                    "type": "stat_mod", "name": "Speedy", "modifiers": {"agility": 10}
                }
            }
        }
        self.world.item_templates["helm_heavy"] = {
            "type": "Armor", "name": "Heavy Helm", "value": 1,
            "properties": {
                "equip_slot": ["head"],
                "equip_effect": {
                    "type": "stat_mod", "name": "Heavy", "modifiers": {"agility": -3}
                }
            }
        }
        
        boots = ItemFactory.create_item_from_template("boots_speed", self.world)
        helm = ItemFactory.create_item_from_template("helm_heavy", self.world)
        
        if boots and helm:
            self.player.inventory.add_item(boots)
            self.player.inventory.add_item(helm)
            
            base_agi = self.player.stats["agility"]
            
            # 2. Equip Boots (+10)
            self.player.equip_item(boots)
            self.assertEqual(self.player.get_effective_stat("agility"), base_agi + 10)
            
            # 3. Equip Helm (-3) -> Net +7
            self.player.equip_item(helm)
            self.assertEqual(self.player.get_effective_stat("agility"), base_agi + 7)
            
            # 4. Unequip Boots (-10) -> Net -3
            self.player.unequip_item("feet")
            self.assertEqual(self.player.get_effective_stat("agility"), base_agi - 3)