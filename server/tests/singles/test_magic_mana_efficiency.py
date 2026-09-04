# tests/singles/test_magic_mana_efficiency.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestMagicManaEfficiency(GameTestBase):
    
    def setUp(self):
        super().setUp()
        self.spell = Spell("check_mana", "Check", "x", mana_cost=10, cooldown=0, effects=[{"type": "heal", "value": 1}], level_required=1, target_type="self")
        register_spell(self.spell)
        self.player.learn_spell("check_mana")
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 100

    def test_cast_consumes_mana(self):
        """Verify success consumes mana."""
        self.player.cast_spell(self.spell, self.player, time.time())
        self.assertEqual(self.player.runtime_state.magic.mana, 90)

    def test_failure_preserves_mana(self):
        """Verify failure (e.g. cooldown/stun) does not consume mana."""
        # Force cooldown via dict manipulation to simulate mid-cooldown state
        self.player.runtime_state.magic.cooldowns["check_mana"] = time.time() + 100.0
        
        result = self.player.cast_spell(self.spell, self.player, time.time())
        
        self.assertFalse(result["success"])
        self.assertEqual(self.player.runtime_state.magic.mana, 100, "Mana should not be consumed on failure.")
