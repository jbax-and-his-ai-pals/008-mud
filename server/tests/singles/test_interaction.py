# tests/singles/test_interaction.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestInteraction(GameTestBase):

    def test_merchant_buy(self):
        """Verify buying items reduces gold and updates inventory."""
        # 1. Setup: Rich player, Merchant in room
        self.player.runtime_state.gold = 500
        
        # Ensure player is in a known valid location
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if merchant:
            self.world.add_npc(merchant)
            # CRITICAL FIX: Set both Region and Room to match player
            merchant.current_region_id = "town"
            merchant.current_room_id = "town_square"
            
            # 2. Initiate Trade
            self.player.trading_with = None
            self.game.process_command("trade Merchant")
            
            # Verify trade started
            self.assertEqual(self.player.trading_with, merchant.obj_id, "Trade failed to start.")
            
            # 3. Buy Item (Potion cost ~15g * multiplier)
            self.game.process_command("buy small healing potion")
            
            # 4. Assert
            self.assertEqual(self.player.inventory.count_item("item_healing_potion_small"), 1)
            self.assertLess(self.player.runtime_state.gold, 500)

    def test_merchant_sell(self):
        """Verify selling items increases gold."""
        # 1. Setup: Poor player with item
        self.player.runtime_state.gold = 0
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"

        gem = ItemFactory.create_item_from_template("item_ruby", self.world) # Value 300, Type: Gem
        if gem: self.player.inventory.add_item(gem)
        
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if merchant:
            self.world.add_npc(merchant)
            merchant.current_region_id = "town"
            merchant.current_room_id = "town_square"
            
            # CRITICAL FIX: Ensure the merchant is configured to buy Gems for this test
            # The default template might not include "Gem" in "buys_item_types"
            buy_types = merchant.properties.get("buys_item_types", [])
            if "Gem" not in buy_types:
                buy_types.append("Gem")
                merchant.properties["buys_item_types"] = buy_types
            
            # 2. Trade
            self.game.process_command("trade Merchant")
            self.assertEqual(self.player.trading_with, merchant.obj_id, "Trade failed to start.")
            
            # 3. Sell
            self.game.process_command("sell ruby")
            
            # 4. Assert
            self.assertEqual(self.player.inventory.count_item("item_ruby"), 0, "Item should be removed from inventory")
            self.assertGreater(self.player.runtime_state.gold, 0, "Gold should increase")

    def test_dialogue_ask(self):
        """Verify the ask command retrieves topic responses."""
        # 1. Setup NPC
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"

        guard = NPCFactory.create_npc_from_template("town_guard", self.world)
        if guard:
            self.world.add_npc(guard)
            guard.current_region_id = "town"
            guard.current_room_id = "town_square"
            
            # 2. Act: Ask about 'job' (common topic)
            self.game.process_command("ask Guard job")
            
            # 3. Assert
            self.assertMessageContains("stand watch")
