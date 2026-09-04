# tests/singles/test_spell_scaling.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.effects import apply_spell_effect

class TestSpellScaling(GameTestBase):

    def setUp(self):
        super().setUp()
        # FIX: Zero out resistance so it doesn't interfere with scaling math
        # Default magic_resist is 2, which caused 10 damage to become 8.
        if self.player:
            self.player.stats["magic_resist"] = 0
            self.player.stats["resistances"] = {}
            self.player.stat_modifiers = {}

    def test_intelligence_scaling(self):
        """Verify that higher Intelligence increases spell effectiveness."""
        if not self.player:
            self.fail("Player not initialized")
            return

        spell = Spell(
            spell_id="test_blast", name="Blast", description="test",
            effects=[{"type": "damage", "value": 10, "damage_type": "magical"}]
        )
        
        # 1. Base scaling (Int 10)
        self.player.stats["intelligence"] = 10
        self.player.stats["spell_power"] = 0
        
        # Patch variation to 0% so we see pure stat math
        with patch('random.uniform', return_value=0.0):
            val_low, _ = apply_spell_effect(self.player, self.player, spell, self.player)
        
        # 2. High scaling (Int 20)
        self.player.stats["intelligence"] = 20
        with patch('random.uniform', return_value=0.0):
            val_high, _ = apply_spell_effect(self.player, self.player, spell, self.player)
            
        # Formula: Base (10) + (Int - 10)//5 + SpellPower
        # Low: 10 + 0 + 0 = 10
        # High: 10 + 2 + 0 = 12
        self.assertEqual(val_low, 10, "Base damage should be 10 when Int is 10.")
        self.assertEqual(val_high, 12, "Damage should be 12 when Int is 20.")
        self.assertGreater(val_high, val_low)

    def test_spell_power_bonus(self):
        """Verify that the Spell Power stat adds directly to effectiveness."""
        if not self.player:
            self.fail("Player not initialized")
            return

        spell = Spell(
            spell_id="test_blast", name="Blast", description="test",
            effects=[{"type": "damage", "value": 10, "damage_type": "magical"}]
        )
        
        self.player.stats["intelligence"] = 10
        self.player.stats["spell_power"] = 5
        
        with patch('random.uniform', return_value=0.0):
            val, _ = apply_spell_effect(self.player, self.player, spell, self.player)
            
        # 10 (base) + 0 (int bonus) + 5 (power) = 15
        self.assertEqual(val, 15, "Damage should be base (10) + spell power (5) = 15.")
