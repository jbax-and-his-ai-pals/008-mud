# tests/singles/test_lockpick_full.py
"""Coverage for engine/items/lockpick.py's Lockpick.use(): the no-target
prompt, a target without pick_lock() being rejected, and a user without
an inventory attribute skipping the on-break removal call."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.lockpick import Lockpick
from engine.items.container import Container
from engine.items.item import Item


class TestLockpickUse(GameTestBase):
    def test_no_target_prompts_for_one(self):
        pick = Lockpick(name="Rusty Pick")
        result = pick.use(self.player, target=None)
        self.assertIn("What do you want to use", result)

    def test_target_without_pick_lock_is_rejected(self):
        pick = Lockpick(name="Rusty Pick")
        plain_item = Item(name="Plain Rock")
        result = pick.use(self.player, target=plain_item)
        self.assertIn("can't use a lockpick", result)

    def test_user_without_inventory_skips_removal_on_break(self):
        pick = Lockpick(name="Rusty Pick", durability=1)
        container = Container(name="Chest", locked=True)
        container.update_property("lock_difficulty", 30)

        class _NoInventoryUser:
            name = "Ghost User"
            def get_skill_level(self, skill_name):
                return 0

        with patch(
            "engine.items.lockpick.SkillSystem.attempt_check_with_margin",
            return_value=(False, "roll failed", -20),
        ):
            with patch("engine.items.lockpick.SkillSystem.grant_xp", return_value=""):
                result = pick.use(_NoInventoryUser(), target=container)  # must not raise
        self.assertIn("snaps in the mechanism", result)


if __name__ == "__main__":
    unittest.main()
