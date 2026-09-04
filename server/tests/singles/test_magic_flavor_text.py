# tests/singles/test_magic_flavor_text.py
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.effects import apply_spell_effect

class TestMagicFlavorText(GameTestBase):

    def test_weakness_flavor_trigger(self):
        """Verify that negative resistance triggers 'weakness' flavor text."""
        if self.player:
            self.player.stats["resistances"] = {"fire": -50}
            self.player.stats["magic_resist"] = 0
            self.player.stats["intelligence"] = 10 
            
            fire_spell = Spell(
                spell_id="test_fire", name="Fire", description="test",
                effects=[{"type": "damage", "value": 10, "damage_type": "fire"}]
            )
            
            val, msg = apply_spell_effect(self.player, self.player, fire_spell, self.player)
            
            self.assertIn("incinerating", msg.lower())

    def test_strong_resistance_flavor_trigger(self):
        """Verify that high resistance triggers 'strong resistance' flavor text."""
        if self.player:
            self.player.stats["resistances"] = {"ice": 75}  # Changed from 'cold' to 'ice' to match config
            self.player.stats["magic_resist"] = 0
            
            ice_spell = Spell(
                spell_id="test_ice", name="Ice", description="test",
                effects=[{"type": "damage", "value": 10, "damage_type": "ice"}] # Changed from 'cold' to 'ice'
            )
            
            val, msg = apply_spell_effect(self.player, self.player, ice_spell, self.player)
            
            self.assertIn("uselessly", msg.lower())
