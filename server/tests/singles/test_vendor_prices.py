# tests/singles/test_vendor_prices.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestVendorPrices(GameTestBase):

    def setUp(self):
        super().setUp()
        self.world.item_templates["overpriced_potion"] = {
            "type": "Consumable", "name": "Overpriced Potion", "value": 10, "weight": 0.5,
            "properties": {"effect_type": "heal", "effect_value": 5, "uses": 1}
        }
        
        self.world.npc_templates["greedy_merchant"] = {
            "name": "Greedy Griz", "faction": "friendly", "level": 1,
            "properties": {
                "is_vendor": True,
                "sells_items": [
                    {"item_id": "overpriced_potion", "price_multiplier": 5.0}
                ]
            }
        }

    def test_vendor_multiplier_application(self):
        """Verify that item costs are calculated using the vendor's specific multiplier."""
        vendor = NPCFactory.create_npc_from_template("greedy_merchant", self.world)
        self.assertIsNotNone(vendor)
        
        if vendor and self.player:
            self.world.add_npc(vendor)
            vendor.current_region_id = self.player.current_region_id
            vendor.current_room_id = self.player.current_room_id
            
            self.game.process_command(f"trade {vendor.name}")
            self.player.runtime_state.gold = 100
            
            # Base value 10 * 5.0 multiplier = 50 gold.
            result = self.game.process_command("buy overpriced potion")
            
            self.assertIsNotNone(result)
            if result:
                self.assertIn("50 gold", result)
            
            self.assertEqual(self.player.runtime_state.gold, 50)
            self.assertEqual(self.player.inventory.count_item("overpriced_potion"), 1)
