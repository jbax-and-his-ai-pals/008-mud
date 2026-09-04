# tests/singles/test_gold_transaction_boundaries.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestGoldTransactionBoundaries(GameTestBase):

    def test_exact_shortfall(self):
        """Verify purchase fails if 1 gold short."""
        vendor = NPCFactory.create_npc_from_template("merchant", self.world)
        if not vendor: return
        
        self.world.add_npc(vendor)
        vendor.current_region_id = self.player.current_region_id
        vendor.current_room_id = self.player.current_room_id
        
        # Setup item cost logic
        # Merchant sells 'item_hunk_bread' (Base Value 1, Mult 1.0 -> Price 1)
        # Let's use something more expensive to be sure.
        # 'item_coiled_rope' (Base 8, Mult 1.0 -> Price 8)
        
        target_item = "coiled rope"
        cost = 8 # Based on default template/merchant config
        
        self.player.gold = cost - 1 # 7 Gold
        
        # Initiate Trade
        self.player.trading_with = vendor.obj_id
        
        # Act
        result = self.game.process_command(f"buy {target_item}")
        
        # Assert
        self.assertIsNotNone(result)
        if result:
            self.assertIn("don't have enough gold", result.lower())
            self.assertEqual(self.player.gold, cost - 1)
            self.assertEqual(self.player.inventory.count_item("item_coiled_rope"), 0)