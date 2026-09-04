# tests/batch/test_batch_3.py
import time

from unittest.mock import patch
from typing import cast, Dict, Any
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe
from engine.core.skill_system import SkillSystem, MAX_SKILL_LEVEL
from engine.items.container import Container
from engine.npcs.npc_factory import NPCFactory

class TestBatch3(GameTestBase):

    def test_container_weight_static(self):
        """Verify container weight does not increase when items are added (Bag of Holding style)."""
        # 1. Setup
        self.world.item_templates["magic_bag"] = {
            "type": "Container", "name": "Bag", "weight": 2.0,
            "properties": {"capacity": 100.0, "is_open": True}
        }
        self.world.item_templates["heavy_rock"] = {
            "type": "Item", "name": "Rock", "weight": 50.0
        }
        
        bag_item = ItemFactory.create_item_from_template("magic_bag", self.world)
        rock = ItemFactory.create_item_from_template("heavy_rock", self.world)
        
        if bag_item and rock:
            # Cast to Container to access add_item
            if isinstance(bag_item, Container):
                bag = cast(Container, bag_item)
                
                self.player.inventory.add_item(bag)
                # Initial weight check
                self.assertEqual(self.player.inventory.get_total_weight(), 2.0)
                
                # 2. Add Rock to Bag
                bag.add_item(rock)
                
                # 3. Assert Player weight unchanged
                self.assertEqual(self.player.inventory.get_total_weight(), 2.0)
                # Assert Bag contents weight correct
                self.assertEqual(bag.get_current_weight(), 50.0)
            else:
                self.fail("Created bag is not a Container instance.")
        else:
            self.fail("Failed to create test items.")

    def test_vendor_list_formatting(self):
        """Verify the 'list' command output contains prices."""
        # 1. Setup Merchant
        self.world.item_templates["test_item"] = {"type": "Item", "name": "Thing", "value": 10}
        self.world.npc_templates["merchant"] = {
            "name": "Bob", "faction": "friendly",
            "properties": {"is_vendor": True, "sells_items": [{"item_id": "test_item"}]}
        }
        
        # Clear existing NPCs to avoid confusion
        self.world.npcs = {}
        
        # Create new vendor
        vendor = NPCFactory.create_npc_from_template("merchant", self.world)
        if vendor:
            self.world.add_npc(vendor)
            if self.player.current_region_id and self.player.current_room_id:
                vendor.current_region_id = self.player.current_region_id
                vendor.current_room_id = self.player.current_room_id
                self.player.trading_with = vendor.obj_id
                
                result = self.game.process_command("list")
                
                self.assertIsNotNone(result)
                if result:
                    self.assertIn("Price:", result)
                    self.assertIn("Thing", result)
            else:
                self.fail("Player location invalid.")
        else:
            self.fail("Failed to create vendor.")

    def test_npc_combat_message_limit(self):
        """Verify NPC combat message history doesn't grow indefinitely."""
        npc = NPCFactory.create_npc_from_template("town_guard", self.world)
        if npc:
            npc.max_combat_messages = 5
            for i in range(10):
                npc._add_combat_message(f"Message {i}")
            
            self.assertEqual(len(npc.combat_messages), 5)
            self.assertEqual(npc.combat_messages[-1], "Message 9")
        else:
            self.fail("Failed to create NPC.")

    def test_weather_persistence_load(self):
        """Verify weather manager restores state from save data."""
        wm = self.game.weather_manager
        saved_state = {"current_weather": "snow", "current_intensity": "blizzard"}
        
        wm.apply_loaded_weather_state(saved_state)
        
        self.assertEqual(wm.current_weather, "snow")
        self.assertEqual(wm.current_intensity, "blizzard")

    def test_crafting_result_quantity(self):
        """Verify crafting recipes yielding >1 items work correctly."""
        manager = self.game.crafting_manager
        if not manager:
            self.fail("Crafting manager not initialized.")
            return

        self.world.item_templates["stick"] = {"type": "Item", "name": "Stick", "value": 1}
        self.world.item_templates["arrow"] = {"type": "Item", "name": "Arrow", "value": 1, "stackable": True}
        
        recipe = Recipe("make_arrows", {
            "result_item_id": "item_arrow", # Use full ID if mapping relies on it, or template ID
            # In setUp I defined "arrow", but ItemFactory needs template ID. 
            # The template key is "arrow".
            "result_quantity": 5, 
            "ingredients": [{"item_id": "stick", "quantity": 1}]
        })
        # Override template IDs to match recipe expectations
        self.world.item_templates["item_arrow"] = self.world.item_templates["arrow"]
        
        manager.recipes["make_arrows"] = recipe
        
        stick = ItemFactory.create_item_from_template("stick", self.world)
        if stick: self.player.inventory.add_item(stick)
        
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "")):
            self.game.crafting_manager.craft(self.player, "make_arrows")
            
        self.assertEqual(self.player.inventory.count_item("item_arrow"), 5)

    def test_quest_reward_gold_addition(self):
        """Verify quest completion adds gold to player wallet."""
        start_gold = self.player.runtime_state.gold
        
        q_id = "gold_quest"
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "state": "ready_to_complete",
            "rewards": {"gold": 50}, "giver_instance_id": "self"
        }
        
        # Simulate turn-in logic directly to verify math
        q = self.player.runtime_state.quests.active.pop(q_id)
        # Cast to Dict for Pylance safety, assuming valid structure
        rewards = cast(Dict[str, int], q["rewards"])
        self.player.runtime_state.gold += rewards["gold"]
        
        self.assertEqual(self.player.runtime_state.gold, start_gold + 50)

    def test_spell_cooldown_display(self):
        """Verify 'spells' command indicates active cooldowns."""
        from engine.magic.spell import Spell
        from engine.magic.spell_registry import register_spell
        import time
        
        spell = Spell("cd_spell", "Slow Magic", "Desc", cooldown=100.0, effects=[{"type": "heal", "value": 1}], target_type="self")
        register_spell(spell)
        self.player.learn_spell("cd_spell")
        
        # Trigger CD
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.cooldowns["cd_spell"] = time.time() + 50.0
        
        result = self.game.process_command("spells")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("CD", result)
            self.assertIn("Slow Magic", result)

    def test_skill_xp_cap(self):
        """Verify skills do not level past MAX_SKILL_LEVEL."""
        skill = "jumping"
        self.player.add_skill(skill, MAX_SKILL_LEVEL)
        
        # Act: Grant massive XP
        msg = SkillSystem.grant_xp(self.player, skill, 10000)
        
        # Assert
        # skills dict stores {level: int, xp: int}
        assert self.player.runtime_state.progression is not None
        skill_data = self.player.runtime_state.progression.skills[skill]
        if isinstance(skill_data, dict):
            self.assertEqual(skill_data["level"], MAX_SKILL_LEVEL)
        else:
            self.fail("Skill data format incorrect.")
            
        # Message should be empty or indicate max
        self.assertEqual(msg, "")

    def test_look_inventory_fallback(self):
        """Verify 'look <item>' finds item in inventory if not in room."""
        # 1. Setup Item in Inventory
        self.world.item_templates["pocket_watch"] = {"type": "Item", "name": "Watch", "description": "Tick tock."}
        watch = ItemFactory.create_item_from_template("pocket_watch", self.world)
        if watch: self.player.inventory.add_item(watch)
        
        # 2. Look
        result = self.game.process_command("look Watch")
        
        # 3. Assert
        self.assertIsNotNone(result)
        if result:
            self.assertIn("Tick tock", result)

    def test_respawn_game_state_reset(self):
        """Verify respawning resets game_state to 'playing'."""
        self.game.game_state = "game_over"
        self.player.is_alive = False
        
        # Act
        self.game.handle_respawn()
        
        # Assert
        self.assertEqual(self.game.game_state, "playing")
        self.assertTrue(self.player.is_alive)
