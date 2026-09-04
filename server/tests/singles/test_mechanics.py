# tests/singles/test_mechanics.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from typing import cast

class TestMechanics(GameTestBase):

    def test_movement(self):
        """Verify the player can move between rooms."""
        start_room = self.player.current_room_id
        
        # Execute move command logic directly via World
        result = self.world.change_room("north")
        
        # Check logic
        self.assertNotEqual(self.player.current_room_id, start_room, "Player failed to move.")
        
        # Check feedback - use Uppercase for Title matching as per DescriptionGenerator
        self.assertIn("NORTH GATE ROAD", result)

    def test_inventory_add_remove(self):
        """Verify adding and dropping items."""
        # Inventory is cleared in setUp, so start count is 0
        
        # Create an item
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        self.assertIsNotNone(potion, "Potion factory failed")
        
        if potion:
            # Add to inventory
            added, msg = self.player.inventory.add_item(potion)
            self.assertTrue(added, f"Failed to add item: {msg}")
            
            # Should be exactly 1 now
            self.assertEqual(self.player.inventory.count_item(potion.obj_id), 1)

            # Remove item
            removed_item, count, _ = self.player.inventory.remove_item(potion.obj_id, 1)
            self.assertIsNotNone(removed_item)
            self.assertEqual(count, 1)
            
            # Should be 0 now
            self.assertEqual(self.player.inventory.count_item(potion.obj_id), 0)

    def test_combat_damage(self):
        """Verify combat math works (Armor reduces damage)."""
        # Create a dummy enemy
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        self.assertIsNotNone(goblin, "Failed to create goblin")
        
        if goblin:
            # Force stats for predictability
            self.player.stats["defense"] = 100 # High defense
            self.player.health = 100
            
            # Goblin hits player for 10 damage
            # High Defense (100) vs Damage (10) -> absorbed down to 0
            damage_taken = self.player.take_damage(10, "physical")
            
            self.assertEqual(damage_taken, 0, "High defense should fully absorb low damage.")
            self.assertEqual(self.player.health, 100)

    def test_command_processor(self):
        """Verify string commands translate to game actions."""
        # Test "look" command
        self.game.process_command("look")
        
        from tests.fixtures import MockRenderer
        mock_renderer = cast(MockRenderer, self.game.renderer)
        
        buffer_text = "\n".join(mock_renderer.message_buffer)
        # Description titles are Uppercase in the new generator
        self.assertIn("TOWN SQUARE", buffer_text)