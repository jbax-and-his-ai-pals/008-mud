# tests/singles/test_stat_caps_and_floors.py
from tests.fixtures import GameTestBase
from engine.config import MIN_ATTACK_COOLDOWN

class TestStatCapsAndFloors(GameTestBase):

    def test_cooldown_floor(self):
        """Verify attack cooldown never drops below global minimum."""
        # 1. Buff Agility to insane levels
        # Normal Agi = 10. Cooldown ~2.0s.
        # Agi 1000 should result in extremely low cooldown.
        self.player.stats["agility"] = 1000
        
        # 2. Get Cooldown
        cd = self.player.get_effective_attack_cooldown()
        
        # 3. Assert Floor
        self.assertGreaterEqual(cd, MIN_ATTACK_COOLDOWN)

    def test_resistance_cap(self):
        """Verify damage logic handles >100% resistance correctly (usually capped or absorption)."""
        # Note: Current logic in GameObject allows negative damage if >100% (healing).
        # OR it clamps resistance. Let's verify current behavior.
        # GameObject.take_damage clamps resistance percent between -100 and 100.
        
        self.player.stats["resistances"] = {"fire": 200} # 200% resistance
        
        # Logic: Clamped to 100%. Damage * (1 - 1.0) = 0.
        damage = self.player.take_damage(10, "fire")
        
        self.assertEqual(damage, 0)
        
        # Ensure it didn't heal (negative damage)
        self.assertGreaterEqual(damage, 0)