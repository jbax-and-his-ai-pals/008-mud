# tests/singles/test_magic_resistance.py
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.effects import apply_spell_effect

class TestMagicResistance(GameTestBase):
    
    def test_magic_resist_mitigation(self):
        """Verify magic_resist stat reduces spell damage flat amount."""
        # Setup: Target with 5 Magic Resist
        self.player.stats["magic_resist"] = 5
        self.player.stats["defense"] = 0 
        
        # NEUTRALIZE SCALING: Set stats that boost spell damage to 0
        # This ensures Base Damage (20) is the only factor before variation
        self.player.stats["intelligence"] = 0
        self.player.stats["spell_power"] = 0
        
        self.player.health = 100
        
        # Create Spell (20 Damage)
        spell = Spell(
            spell_id="test_bolt", name="Bolt", description="Zap",
            effects=[{"type": "damage", "value": 20, "damage_type": "magical"}]
        )
        
        # Act: Cast on player
        value, msg = apply_spell_effect(self.player, self.player, spell, self.player)
        
        # Assert: 
        # Base: 20. 
        # Variation (0.1): 18 to 22.
        # Reduction: -5.
        # Expected Result: 13 to 17.
        
        self.assertGreaterEqual(value, 13)
        self.assertLessEqual(value, 17)

    def test_elemental_resistance_percent(self):
        """Verify percentage-based elemental resistance."""
        # Setup: 50% Fire Resistance
        self.player.stats["resistances"] = {"fire": 50}
        self.player.stats["magic_resist"] = 0 
        
        # Neutralize scaling
        self.player.stats["intelligence"] = 0
        self.player.stats["spell_power"] = 0
        
        self.player.health = 100
        
        spell = Spell(
            spell_id="test_fire", name="Fire", description="Burn",
            effects=[{"type": "damage", "value": 40, "damage_type": "fire"}]
        )
        
        # Act
        value, msg = apply_spell_effect(self.player, self.player, spell, self.player)
        
        # Assert
        # Base: 40.
        # Variation (0.1): 36 to 44.
        # Resist 50%: 18 to 22.
        
        self.assertGreaterEqual(value, 18)
        self.assertLessEqual(value, 22)
