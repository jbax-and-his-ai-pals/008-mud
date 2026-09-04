# tests/singles/test_respawn_equipment_retention.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestRespawnEquipmentRetention(GameTestBase):

    def test_gear_stays_after_death(self):
        """Verify player keeps equipped items after respawning."""
        # 1. Create and Equip Item
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword, "Failed to create sword")
        
        if sword:
            self.player.inventory.add_item(sword)
            success, msg = self.player.equip_item(sword, "main_hand")
            self.assertTrue(success, f"Failed to equip sword: {msg}")
            
            # Verify equipped state
            self.assertEqual(self.player.equipment["main_hand"], sword)
            
            # 2. Die
            self.player.die(self.world)
            self.assertFalse(self.player.is_alive)
            
            # 3. Respawn
            self.player.respawn()
            self.assertTrue(self.player.is_alive)
            
            # 4. Assert
            equipped_item = self.player.equipment.get("main_hand")
            self.assertIsNotNone(equipped_item, "Main hand should not be empty after respawn")
            
            if equipped_item:
                self.assertEqual(equipped_item.obj_id, sword.obj_id, "Equipped item ID should match original sword.")