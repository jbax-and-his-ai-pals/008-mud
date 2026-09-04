# tests/singles/test_mercantile_logic.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from typing import cast, Optional
from engine.npcs.npc import NPC

class TestMercantileLogic(GameTestBase):
    
    def setUp(self):
        super().setUp()
        
        # Create a Blacksmith NPC who only buys Weapons/Armor/Material
        vendor_candidate = NPCFactory.create_npc_from_template("blacksmith", self.world)
        
        if not vendor_candidate:
            # Fallback if template missing
            vendor_candidate = NPCFactory.create_npc_from_template("wandering_villager", self.world)
            
        # Ensure we actually have an NPC before proceeding
        if vendor_candidate:
            self.vendor: Optional[NPC] = vendor_candidate
            # Ensure properties exist
            if "buys_item_types" not in self.vendor.properties:
                 self.vendor.properties["buys_item_types"] = ["Weapon", "Armor", "Material"]
            self.vendor.properties["is_vendor"] = True
            
            self.world.add_npc(self.vendor)
            # Ensure safe access to IDs
            if self.player.current_region_id and self.player.current_room_id:
                self.vendor.current_region_id = self.player.current_region_id
                self.vendor.current_room_id = self.player.current_room_id
            
            # Start trading
            self.player.trading_with = self.vendor.obj_id
        else:
            self.vendor = None

    def test_vendor_rejects_invalid_type(self):
        """Verify vendor rejects items not in their buy list."""
        if not self.vendor:
            self.fail("Setup failed: Could not create vendor.")
            return

        # Create a Consumable (Apple) - Blacksmiths shouldn't buy food usually
        apple = ItemFactory.create_item_from_template("item_ripe_apple", self.world)
        self.assertIsNotNone(apple, "Failed to create apple item.")
        
        if apple:
            # Explicitly ensure Blacksmith config doesn't include Consumable for this test
            self.vendor.properties["buys_item_types"] = ["Weapon", "Armor", "Material"]
            
            self.player.inventory.add_item(apple)
            
            # Attempt Sell
            result = self.game.process_command(f"sell {apple.name}")
            
            # Assert Rejection
            self.assertIsNotNone(result)
            if result:
                self.assertIn("not interested", result)
            
            self.assertEqual(self.player.inventory.count_item(apple.obj_id), 1, "Item should not be sold.")

    def test_vendor_buys_valid_type(self):
        """Verify vendor buys valid items and gold increases."""
        if not self.vendor:
            self.fail("Setup failed: Could not create vendor.")
            return

        # FIX: Use a Weapon (Iron Sword) instead of Ingot (Item). 
        # Vendors filter by Class Name (Weapon, Armor), not property category.
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword, "Failed to create sword item.")
        
        if sword:
            self.player.inventory.add_item(sword)
            start_gold = self.player.runtime_state.gold
            
            # Attempt Sell
            result = self.game.process_command(f"sell {sword.name}")
            
            # Assert Success
            self.assertIsNotNone(result)
            if result:
                self.assertIn("You sell", result)
            
            self.assertGreater(self.player.runtime_state.gold, start_gold)
            self.assertEqual(self.player.inventory.count_item(sword.obj_id), 0)
