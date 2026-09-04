# tests/singles/test_equipment_slot_swapping.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestEquipmentSlotSwapping(GameTestBase):

    def test_equip_to_secondary_slot(self):
        """Verify items fill empty valid slots before displacing existing ones."""
        # Setup: Two daggers
        self.world.item_templates["test_dagger"] = {
            "type": "Weapon", "name": "dagger", "value": 5,
            "properties": { "equip_slot": ["main_hand", "off_hand"] }
        }
        
        d1 = ItemFactory.create_item_from_template("test_dagger", self.world)
        d2 = ItemFactory.create_item_from_template("test_dagger", self.world)
        
        if d1 and d2 and self.player:
            d1.obj_id = "d1"; d2.obj_id = "d2"
            self.player.inventory.add_item(d1)
            self.player.inventory.add_item(d2)
            
            # 1. Equip first dagger -> main_hand (default)
            self.player.equip_item(d1)
            self.assertEqual(self.player.equipment["main_hand"], d1)
            
            # 2. Equip second dagger -> should go to off_hand because main is full
            self.player.equip_item(d2)
            self.assertEqual(self.player.equipment["off_hand"], d2)
            self.assertEqual(self.player.equipment["main_hand"], d1)

    def test_explicit_slot_selection(self):
        """Verify equipping specifically to a slot works."""
        shield = ItemFactory.create_item_from_template("item_lizardfolk_shield", self.world)
        if shield and self.player:
            self.player.inventory.add_item(shield)
            
            # "equip shield to off hand"
            self.game.process_command(f"equip {shield.name} to off_hand")
            self.assertEqual(self.player.equipment["off_hand"], shield)