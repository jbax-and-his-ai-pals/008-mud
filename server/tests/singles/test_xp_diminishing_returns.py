# tests/singles/test_xp_diminishing_returns.py
from tests.fixtures import GameTestBase
from engine.utils.utils import calculate_xp_gain

class TestXPDiminishingReturns(GameTestBase):

    def test_gray_mob_xp(self):
        """Verify high-level players get minimal XP for low-level mobs."""
        # Level 50 player vs Level 1 mob
        xp = calculate_xp_gain(killer_level=50, target_level=1, target_max_health=10)
        
        # Logic: Base XP is low. Multiplier for Gray (diff > 5 or so) is 0.2
        # It shouldn't be zero, but should be very low.
        self.assertGreater(xp, 0)
        self.assertLess(xp, 10) 

    def test_purple_mob_xp(self):
        """Verify under-leveled players get massive XP bonuses."""
        # Level 1 player vs Level 5 mob (Purple difficulty)
        xp = calculate_xp_gain(killer_level=1, target_level=5, target_max_health=100)
        
        # Base would be ~25. Purple multiplier is 2.5x.
        self.assertGreater(xp, 50)