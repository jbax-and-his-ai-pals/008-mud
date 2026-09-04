# tests/singles/test_xp_scaling.py
from tests.fixtures import GameTestBase
from engine.utils.utils import calculate_xp_gain
from engine.config import MIN_XP_GAIN

class TestXPScaling(GameTestBase):

    def test_xp_calculation_logic(self):
        """Verify XP rewards scale based on level difference."""
        # Base Health = 100
        # XP Divisor = 5 (Config)
        # Level Multiplier = 5 (Config)
        # Base XP = (100 // 5) + (TargetLvl * 5) = 20 + 25 = 45.
        
        target_health = 100
        
        # 1. Even Match (Level 5 vs 5) -> Yellow (1.0x)
        xp_even = calculate_xp_gain(killer_level=5, target_level=5, target_max_health=target_health)
        self.assertEqual(xp_even, 45)

        # 2. High Level Player (Level 50 vs 5) -> Gray (0.2x)
        # Base = 45. Multiplier 0.2. Total 9.
        xp_trivial = calculate_xp_gain(killer_level=50, target_level=5, target_max_health=target_health)
        self.assertEqual(xp_trivial, 9)

        # 3. Underleveled Player (Level 1 vs 5)
        # Diff = 4. Config map: Diff >= 3 is "purple" (2.5x multiplier)
        # Base = 45. Multiplier 2.5. Total = 112.5 -> 112
        xp_hard = calculate_xp_gain(killer_level=1, target_level=5, target_max_health=target_health)
        self.assertEqual(xp_hard, int(45 * 2.50)) # 112

    def test_min_xp(self):
        """Verify XP never drops below minimum."""
        # Trivial target with low health
        xp = calculate_xp_gain(killer_level=100, target_level=1, target_max_health=5)
        self.assertGreaterEqual(xp, MIN_XP_GAIN)