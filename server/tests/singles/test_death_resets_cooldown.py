# tests/singles/test_death_resets_cooldown.py
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestDeathResetsCooldowns(GameTestBase):

    def setUp(self):
        super().setUp()
        self.long_spell = Spell(
            spell_id="long_cd", name="Ult", description="...",
            mana_cost=0, cooldown=100.0, effects=[{"type": "heal", "value": 1}], level_required=1,
            target_type="self"
        )
        register_spell(self.long_spell)
        self.player.learn_spell("long_cd")

    def test_respawn_clears_timers(self):
        """Verify dying resets spell cooldowns."""
        # 1. Trigger Cooldown
        self.player.cast_spell(self.long_spell, self.player, time.time())
        self.assertFalse(self.player.can_cast_spell(self.long_spell, time.time() + 1.0)[0])
        
        # 2. Die
        self.player.die(self.world)
        
        # 3. Respawn
        self.player.respawn()
        
        # 4. Assert
        can_cast, _ = self.player.can_cast_spell(self.long_spell, time.time() + 2.0)
        self.assertTrue(can_cast, "Cooldowns should be cleared on respawn.")
