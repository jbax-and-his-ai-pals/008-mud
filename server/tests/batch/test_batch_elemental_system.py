# tests/batch/test_batch_elemental_system.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.world.room import Room
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.npcs.npc_factory import NPCFactory

class TestBatchElementalSystem(GameTestBase):

    def test_fire_vulnerability(self):
        """Verify Fire damage deals more to Ice-weak targets."""
        # 0. Neutralize Player Scaling for deterministic math
        self.player.stats["intelligence"] = 10 # No bonus from Int
        self.player.stats["spell_power"] = 0   # No bonus from Power
        
        # 1. Setup Fire Spell
        # Explicitly pass 'effects' to avoid Pylance unpacking confusion
        fireball = Spell("test_fireball", "Fireball", "x", effects=[{"type": "damage", "value": 20, "damage_type": "fire"}])
        register_spell(fireball)
        self.player.runtime_state.magic.known_spells.add("test_fireball")
        
        # 2. Setup Target with Weakness (-50% Fire Resist)
        ice_golem = NPCFactory.create_npc_from_template("goblin", self.world) # Use goblin as base
        
        # Pylance Guard: Ensure ice_golem is not None
        self.assertIsNotNone(ice_golem)
        if ice_golem:
            # Ensure target has no flat resist interfering
            ice_golem.stats["magic_resist"] = 0
            ice_golem.stats["resistances"] = {"fire": -50}
            ice_golem.health = 100
            
            # 3. Cast
            with patch('random.uniform', return_value=0.0): # No variance
                 self.player.cast_spell(fireball, ice_golem, time.time(), self.world)
                 
            # Calculation: 
            # Base 20. Stats 0.
            # Target Flat Resist 0.
            # Target Percent Resist -50% -> Multiplier 1.5.
            # Final: 20 * 1.5 = 30 Damage.
            # 100 - 30 = 70.
            self.assertEqual(ice_golem.health, 70)

    def test_environmental_hazard_damage(self):
        """Verify standing in a 'fire' room damages player without resist."""
        # 0. Neutralize Player Defenses
        self.player.stats["magic_resist"] = 0
        self.player.stats["resistances"] = {"fire": 0}
        self.player.health = 100
        
        room = Room("Volcano", "Hot.", obj_id="volcano")
        room.properties["hazard_type"] = "extreme_heat"
        room.properties["hazard_damage"] = 10
        
        # Apply Hazard
        msg = room.apply_hazards(self.player, time.time())
        
        self.assertIsNotNone(msg)
        if msg: self.assertIn("heat scorches", msg)
        
        # 100 - 10 = 90
        self.assertEqual(self.player.health, 90)

    def test_environmental_hazard_immunity(self):
        """Verify 100% Fire Resist negates volcanic damage."""
        room = Room("Volcano", "Hot.", obj_id="volcano")
        room.properties["hazard_type"] = "extreme_heat"
        room.properties["hazard_damage"] = 10
        
        self.player.health = 100
        # Set 100% resist
        self.player.stats["resistances"] = {"fire": 100}
        self.player.stats["magic_resist"] = 0
        
        msg = room.apply_hazards(self.player, time.time())
        
        # Should return None (no damage taken)
        self.assertIsNone(msg)
        self.assertEqual(self.player.health, 100)

    def test_multi_effect_spell(self):
        """Verify a spell can do Damage AND Dot."""
        effects_list = [
            {"type": "damage", "value": 10, "damage_type": "physical"},
            {"type": "apply_dot", "dot_name": "Burn", "dot_damage_per_tick": 5}
        ]
        
        # Explicitly pass 'effects' as a named argument
        combo_spell = Spell("combo", "Combo", "x", effects=effects_list)
        
        register_spell(combo_spell)
        self.player.runtime_state.magic.known_spells.add("combo")
        
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        
        # Pylance Guard: Ensure target is not None
        self.assertIsNotNone(target)
        if target:
            target.health = 100
            
            self.player.cast_spell(combo_spell, target, time.time(), self.world)
            
            # Immediate Damage
            self.assertLess(target.health, 100)
            # Dot Applied
            self.assertTrue(target.has_effect("Burn"))
