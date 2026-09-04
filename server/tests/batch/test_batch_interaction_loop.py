# tests/batch/test_batch_interaction_loop.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.world.room import Room
from engine.world.region import Region
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestBatchInteractionLoop(GameTestBase):

    def test_environmental_spell_reaction(self):
        """Verify casting Ice on a Water room changes properties."""
        room = Room("Lake", "Water.", obj_id="lake")
        # Exit blocked by swimming req
        room.exits["north"] = "island"
        room.properties["exit_requirements"] = {"north": {"type": "skill", "skill_name": "swimming", "difficulty": 50}}
        
        # Define reaction
        room.properties["env_interactions"] = {
            "ice": {
                "type": "clear_exit_req",
                "direction": "north",
                "duration": 5.0,
                "message": "The water freezes solid!"
            }
        }
        
        # Player Setup
        self.player.current_region_id = "test"
        self.player.current_room_id = "lake"
        
        # Fix: Use real Region object to satisfy type checker
        test_region = Region("Test", "Test Region", obj_id="test")
        test_region.add_room("lake", room)
        self.world.add_region("test", test_region)
        
        self.world.current_room_id = "lake"
        
        # Cast Ice
        ice_spell = Spell("freeze", "Freeze", "x", effects=[{"type": "damage", "damage_type": "ice", "value": 0}])
        # We need to simulate the Cast Command logic calling apply_spell_effect on the ROOM
        from engine.magic.effects import apply_spell_effect
        
        # Act
        val, msg = apply_spell_effect(self.player, room, ice_spell, self.player)
        
        # Assert
        self.assertIn("freezes solid", msg)
        self.assertNotIn("north", room.properties["exit_requirements"])
        
        # Wait for Revert
        room.update(6.0)
        self.assertIn("north", room.properties["exit_requirements"])

    def test_hydra_regen_mechanic(self):
        """Verify Fire damage removes a Regeneration buff tag."""
        hydra = NPCFactory.create_npc_from_template("goblin", self.world) # Base template
        self.assertIsNotNone(hydra)
        if hydra:
            hydra.health = 50
            hydra.max_health = 100
            
            # Add Regen Buff
            hydra.apply_effect({"name": "Regen", "type": "hot", "tags": ["regen"], "heal_per_tick": 10}, time.time())
            self.assertTrue(hydra.has_effect("Regen"))
            
            # Define Reactivity
            hydra.properties["damage_reactions"] = {
                "fire": {"action": "remove_effect_tag", "tag": "regen"}
            }
            
            # Hit with Fire
            hydra.take_damage(10, "fire")
            
            # Assert Buff Gone
            self.assertFalse(hydra.has_effect("Regen"))

    def test_salvage_mechanic(self):
        """Verify salvaging an item yields materials."""
        # Setup Item
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword)
        
        if sword:
            self.player.inventory.add_item(sword)
            
            # Setup Material Template (if not exists)
            self.world.item_templates["item_iron_ingot"] = {"type": "Item", "name": "Iron Ingot"}
            
            # Act
            self.game.crafting_manager.salvage(self.player, sword)
            
            # Assert
            self.assertEqual(self.player.inventory.count_item("item_iron_sword"), 0)
            self.assertGreater(self.player.inventory.count_item("item_iron_ingot"), 0)