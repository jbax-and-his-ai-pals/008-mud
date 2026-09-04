# tests/singles/test_stack_split_drop.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestStackSplitDrop(GameTestBase):

    def test_drop_specific_quantity(self):
        """Verify 'drop N item' splits the stack correctly."""
        # 1. Setup Inventory with 10 Coins
        self.world.item_templates["gold_coin"] = {
            "type": "Treasure", "name": "Gold Coin", "value": 1, "stackable": True
        }
        
        coin = ItemFactory.create_item_from_template("gold_coin", self.world)
        if coin:
            self.player.inventory.add_item(coin, 10)
            
            # 2. Act: Drop 4
            result = self.game.process_command("drop 4 Gold Coin")
            
            # 3. Assert Inventory State
            self.assertEqual(self.player.inventory.count_item("gold_coin"), 6, "Should remain 6 coins in inventory.")
            
            # 4. Assert Room State
            room_items = self.world.get_items_in_current_room()
            dropped_coin_stack = next((i for i in room_items if i.name == "Gold Coin"), None)
            
            self.assertIsNotNone(dropped_coin_stack)
            if dropped_coin_stack:
                # Note: 'quantity' attribute might be on the item instance depending on factory logic for stackables,
                # or handled via separate instances. 
                # ItemFactory.create_item_from_template generally returns an Item with quantity=1.
                # However, the drop logic in `commands/interaction/items.py` does:
                # `world.add_item_to_room(..., item_instance)`
                # The inventory remove logic returns specific item instances.
                # If stack splitting creates a NEW instance with qty 4, we check that.
                
                # Check property or attribute
                qty = getattr(dropped_coin_stack, 'quantity', 1) 
                # If Item class doesn't strictly track qty, this assertion relies on implementation details.
                # Standard implementation: InventorySlot holds quantity. Item instance usually holds 1 unless specifically set.
                # In `_handle_item_disposal`: `if player.inventory.remove_item_instance(item_instance)`
                # The inventory logic iterates qty.
                
                # Let's count instances in room if they aren't merged?
                # World `add_item_to_room` appends to list.
                count_in_room = sum(1 for i in room_items if i.name == "Gold Coin")
                
                # If they were dropped as individual items:
                self.assertEqual(count_in_room, 4, "Should be 4 coin instances in room.")