# tests/singles/test_spell_cost_check.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestSpellCostCheck(GameTestBase):

    def setUp(self):
        super().setUp()
        # FIX: Set target_type="self" so cast_spell doesn't block casting on player
        self.spell = Spell(
            spell_id="cost_test", name="Costly", description="x",
            mana_cost=10, effects=[{"type": "damage", "value": 1}], level_required=1,
            target_type="self"
        )
        register_spell(self.spell)
        self.player.learn_spell("cost_test")

    def test_insufficient_mana(self):
        """Verify casting fails if mana is just below cost."""
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 9
        
        can_cast, msg = self.player.can_cast_spell(self.spell, time.time())
        self.assertFalse(can_cast)
        self.assertIn("Not enough mana", msg)

    def test_exact_mana(self):
        """Verify casting succeeds if mana matches cost exactly."""
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 10
        
        can_cast, _ = self.player.can_cast_spell(self.spell, time.time())
        self.assertTrue(can_cast)
        
        # Execute cast to verify consumption
        result = self.player.cast_spell(self.spell, self.player, time.time())
        self.assertTrue(result["success"], f"Cast failed: {result.get('message')}")
        self.assertEqual(self.player.runtime_state.magic.mana, 0)
