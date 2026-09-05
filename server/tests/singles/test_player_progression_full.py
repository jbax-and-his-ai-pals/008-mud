# tests/singles/test_player_progression_full.py
"""Coverage for engine/player/progression.py: gain_experience/level_up/
add_skill/get_skill_level's no-progression-aspect guards, add_skill's
increment-existing-skill branch, and get_skill_level's unknown-skill
branch."""

import unittest

from tests.fixtures import GameTestBase


class TestNoProgressionAspectGuards(GameTestBase):
    def setUp(self):
        super().setUp()
        self.original_progression = self.player.runtime_state.progression
        self.player.runtime_state.progression = None

    def tearDown(self):
        self.player.runtime_state.progression = self.original_progression
        super().tearDown()

    def test_gain_experience_returns_false_and_empty_string(self):
        self.assertEqual(self.player.gain_experience(100), (False, ""))

    def test_level_up_returns_empty_string(self):
        self.assertEqual(self.player.level_up(), "")

    def test_add_skill_is_a_noop(self):
        self.player.add_skill("crafting", 1)  # must not raise

    def test_get_skill_level_returns_zero(self):
        self.assertEqual(self.player.get_skill_level("crafting"), 0)


class TestAddSkill(GameTestBase):
    def test_incrementing_an_existing_skill_adds_to_its_level(self):
        self.player.add_skill("crafting", 2)
        self.player.add_skill("crafting", 3)
        self.assertEqual(self.player.runtime_state.progression.skills["crafting"]["level"], 5)


class TestGetSkillLevel(GameTestBase):
    def test_unknown_skill_returns_zero(self):
        self.assertEqual(self.player.get_skill_level("totally_bogus_skill_xyz"), 0)


if __name__ == "__main__":
    unittest.main()
