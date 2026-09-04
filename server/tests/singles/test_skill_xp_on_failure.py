# tests/singles/test_skill_xp_on_failure.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.core.skill_system import SkillSystem

class TestSkillXPOnFailure(GameTestBase):

    def test_lockpicking_fail_reward(self):
        """Verify failing a lockpick attempt still grants 'consolation' XP."""
        # 1. Initialize Skill at 0
        skill = "lockpicking"
        self.player.runtime_state.progression.skills[skill] = {"level": 1, "xp": 0}
        
        # 2. Mock a failure
        # attempt_check returns (False, msg)
        with patch('random.randint', return_value=0): # Force low roll
            success, _ = SkillSystem.attempt_check(self.player, skill, 100) # Impossible DC
            self.assertFalse(success)
            
            # Manually trigger the grant logic usually found in the item/command
            # In item logic (Lockpick.use), it calls grant_xp(user, "lockpicking", 2) on failure
            SkillSystem.grant_xp(self.player, skill, 2)
            
        # 3. Verify XP increased
        self.assertEqual(self.player.runtime_state.progression.skills[skill]["xp"], 2, "Should gain small XP on failure.")
