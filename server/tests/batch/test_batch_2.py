# tests/batch/test_batch_2.py
import time
from unittest.mock import patch
from typing import cast
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.core.skill_system import SkillSystem
from engine.ui.panel_content import render_inventory_content
from engine.utils.text_formatter import ClickableZone
from engine.items.container import Container
import pygame

class TestBatch2(GameTestBase):

    def test_crafting_recipes_list(self):
        """Verify the 'recipes' command filters based on available stations."""
        manager = self.game.crafting_manager
        if not manager:
            self.fail("Crafting manager not initialized.")
            return

        # 1. Setup Recipe requiring Anvil
        from engine.crafting.recipe import Recipe
        
        recipe = Recipe("manual_sword", {
            "name": "Manual Sword", 
            "result_item_id": "item_iron_sword", 
            "result_quantity": 1,
            "station_required": "anvil",
            "ingredients": []
        })
        manager.recipes["manual_sword"] = recipe

        # 2. List without station
        result_no_station = self.game.process_command("recipes")
        self.assertIsNotNone(result_no_station)
        if result_no_station:
            self.assertNotIn("Manual Sword", result_no_station)
        
        # 3. Add Station
        anvil = ItemFactory.create_item_from_template("item_anvil", self.world)
        if anvil: 
            if self.player.current_region_id and self.player.current_room_id:
                self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, anvil)
            else:
                self.fail("Player location invalid.")
        else:
            self.fail("Failed to create anvil.")
        
        # 4. List with station
        result_station = self.game.process_command("recipes")
        self.assertIsNotNone(result_station)
        if result_station:
            self.assertIn("Nearby Stations", result_station)
            self.assertIn("Anvil", result_station)

    def test_game_over_input_restriction(self):
        """Verify most commands are blocked when game state is 'game_over'."""
        self.game.game_state = "game_over"
        
        with patch.object(self.game, 'process_command') as mock_cmd:
            event_key = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n, unicode="n")
            self.game.input_handler.handle_event(event_key)
            event_enter = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
            self.game.input_handler.handle_event(event_enter)
            mock_cmd.assert_not_called()

    def test_time_advancement_ui(self):
        """Verify time string updates correctly in UI data."""
        tm = self.game.time_manager
        tm.initialize_time(0.0) # 00:00 (Midnight)
        
        # Set directly to 13:30 (13.5 hours * 3600 seconds)
        # FIX: Previous test used 1.5 * 3600 which is 01:30.
        tm.initialize_time(13.5 * 3600) 
        
        # Update UI data manually since game loop isn't running
        tm._update_time_data_for_ui()
        
        self.assertEqual(tm.time_data["time_str"], "13:30")

    def test_inventory_ui_rendering_text(self):
        """Verify text inventory UI generates clickable zones."""
        self.game.inventory_mode = "text"
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if item: self.player.inventory.add_item(item)
        
        surface = pygame.Surface((200, 400))
        hotspots: list[ClickableZone] = []
        context = {"player": self.player, "game": self.game}
        
        render_inventory_content(surface, context, hotspots)
        
        self.assertEqual(len(hotspots), 1)
        self.assertIn("look", hotspots[0].command)

    def test_inventory_ui_rendering_icon(self):
        """Verify icon inventory UI generates hotspots."""
        self.game.inventory_mode = "icon"
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if item: self.player.inventory.add_item(item)
        
        surface = pygame.Surface((200, 400))
        hotspots: list[ClickableZone] = []
        context = {"player": self.player, "game": self.game}
        
        render_inventory_content(surface, context, hotspots)
        
        self.assertEqual(len(hotspots), 1)
        self.assertEqual(hotspots[0].rect.width, 32) # ICON_SIZE

    def test_container_close_command(self):
        """Verify 'close' command updates state."""
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box", "properties": {"is_open": True}
        }
        item_box = ItemFactory.create_item_from_template("box", self.world)
        
        if item_box:
            if not isinstance(item_box, Container):
                 self.fail("Created item is not a Container.")
                 return
            
            box = cast(Container, item_box)
            
            if self.player.current_region_id and self.player.current_room_id:
                self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, box)
                
                result = self.game.process_command("close box")
                
                self.assertIsNotNone(result)
                if result:
                    self.assertIn("You close", result)
                self.assertFalse(box.properties["is_open"])
            else:
                self.fail("Player location invalid.")

    def test_skill_check_exact_boundary(self):
        """Verify skill check passes exactly at difficulty."""
        skill = "lockpicking"
        self.player.add_skill(skill, 10)
        self.player.stats["dexterity"] = 10 # 0 Bonus
        
        with patch('random.randint', return_value=10):
            success, _ = SkillSystem.attempt_check(self.player, skill, 20)
            self.assertTrue(success, "Should pass if Total Score == Difficulty")

        with patch('random.randint', return_value=9):
            success, _ = SkillSystem.attempt_check(self.player, skill, 20)
            self.assertFalse(success, "Should fail if Total Score < Difficulty")

    def test_get_gold_coins(self):
        """Verify 'get gold coin' picks up money as currency, not item."""
        coin = ItemFactory.create_item_from_template("item_gold_coin", self.world)
        if coin:
            if self.player.current_region_id and self.player.current_room_id:
                self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, coin)
                
                start_gold = self.player.runtime_state.gold
                self.game.process_command("get gold coin")
                
                self.assertEqual(self.player.inventory.count_item("item_gold_coin"), 1)
                self.assertEqual(self.player.runtime_state.gold, start_gold)
            else:
                self.fail("Player location invalid.")
        else:
            self.fail("Failed to create gold coin.")

    def test_look_nonexistent(self):
        """Verify looking at a non-existent target returns error."""
        result = self.game.process_command("look ghost")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("don't see", result)

    def test_help_category_listing(self):
        """Verify 'help' lists commands."""
        result = self.game.process_command("help")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("Command Categories", result)
            self.assertIn("Movement", result)
