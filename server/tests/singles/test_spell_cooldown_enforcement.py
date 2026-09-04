# tests/singles/test_spell_cooldown_enforcement.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestSpellCooldownEnforcement(GameTestBase):

    def setUp(self):
        super().setUp()
        # FIX: Set target_type="self" so cast_spell allows casting on player
        self.spell = Spell(
            spell_id="cd_test", name="Slow Spell", description="x",
            mana_cost=0, cooldown=10.0, effects=[{"type": "damage", "value": 1}], level_required=1,
            target_type="self"
        )
        register_spell(self.spell)
        self.player.learn_spell("cd_test")

    def test_cooldown_lifecycle(self):
        """Verify cast -> cooldown -> wait -> cast."""
        now = time.time()
        
        # 1. First Cast (Success)
        can_cast, _ = self.player.can_cast_spell(self.spell, now)
        self.assertTrue(can_cast)
        
        result = self.player.cast_spell(self.spell, self.player, now)
        self.assertTrue(result["success"], "First cast should succeed")
        
        # 2. Immediate Recast (Fail)
        can_cast_immediate, msg = self.player.can_cast_spell(self.spell, now + 1.0)
        self.assertFalse(can_cast_immediate)
        self.assertIn("cooldown", msg)
        
        # 3. Wait (Success)
        future = now + 11.0
        can_cast_later, _ = self.player.can_cast_spell(self.spell, future)
        self.assertTrue(can_cast_later, "Cooldown should expire.")
