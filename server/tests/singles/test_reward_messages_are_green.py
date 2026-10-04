"""What a kill pays out is told in green, however it was earned.

The player's own blow told its experience and money in green and a share earned another way (a companion's kill,
a spell's) did not, so the same line was green one time and white the next.
"""

import unittest

from engine.config import FORMAT_RESET, FORMAT_SUCCESS
from engine.core import kill_credit
from engine.npcs.npc_factory import NPCFactory
from engine.utils.utils import calculate_xp_gain
from tests.fixtures import GameTestBase


class TestRewardsAreGreen(GameTestBase):
    def test_a_share_of_a_kill_is_told_in_green_the_experience_and_the_money(self):
        victim = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="paid_goblin")
        self.world.add_npc(victim)
        told = kill_credit.award_participants(
            self.world, victim, [(self.player, 1.0)], formula=calculate_xp_gain, gold=7, inline=self.player)
        lines = [line for line in told.splitlines() if line.strip()]
        rewards = [line for line in lines if "experience" in line or self.world.currency_name() in line]
        self.assertGreaterEqual(len(rewards), 2, told)
        for line in rewards:
            self.assertTrue(line.startswith(FORMAT_SUCCESS) and line.endswith(FORMAT_RESET), repr(line))


if __name__ == "__main__":
    unittest.main()
