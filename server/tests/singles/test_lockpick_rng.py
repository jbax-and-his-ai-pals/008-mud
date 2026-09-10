# tests/singles/test_lockpick_rng.py
"""Coverage for Lockpick's durability mechanic: a failed attempt costs
durability scaled by how badly it missed, a success costs nothing, and
exhausting durability destroys the specific pick instance."""

from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.lockpick import Lockpick
from engine.items.container import Container


class TestLockpickDurability(GameTestBase):
    def _box(self, difficulty=50):
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box",
            "properties": {"locked": True, "lock_difficulty": difficulty},
        }
        return ItemFactory.create_item_from_template("box", self.world)

    def test_pick_breaks_when_durability_is_exhausted(self):
        box = self._box()
        pick = Lockpick("pick", "Pick", durability=1)
        self.player.inventory.add_item(pick)

        with patch(
            "engine.items.lockpick.SkillSystem.attempt_check_with_margin",
            return_value=(False, "", -5),
        ):
            msg = pick.use(self.player, box)

        self.assertIn("snaps", msg)
        self.assertEqual(self.player.inventory.count_item("pick"), 0)

    def test_pick_survives_a_minor_failure(self):
        box = self._box()
        pick = Lockpick("pick", "Pick", durability=10)
        self.player.inventory.add_item(pick)

        with patch(
            "engine.items.lockpick.SkillSystem.attempt_check_with_margin",
            return_value=(False, "", -5),  # small miss -> loss of 1 (max(1, 5 // 10))
        ):
            msg = pick.use(self.player, box)

        self.assertNotIn("snaps", msg)
        self.assertIn("lockpick durability: 9/10", msg)
        self.assertEqual(self.player.inventory.count_item("pick"), 1)
        self.assertEqual(pick.durability, 9)

    def test_a_worse_failure_costs_more_durability(self):
        box = self._box()
        pick = Lockpick("pick", "Pick", durability=100)
        self.player.inventory.add_item(pick)

        with patch(
            "engine.items.lockpick.SkillSystem.attempt_check_with_margin",
            return_value=(False, "", -47),  # big miss -> loss of 4 (max(1, 47 // 10))
        ):
            pick.use(self.player, box)

        self.assertEqual(pick.durability, 96)

    def test_success_costs_no_durability(self):
        box = self._box()
        pick = Lockpick("pick", "Pick", durability=5)
        self.player.inventory.add_item(pick)

        with patch(
            "engine.items.lockpick.SkillSystem.attempt_check_with_margin",
            return_value=(True, "", 12),
        ), patch("engine.items.lockpick.SkillSystem.grant_xp", return_value=""):
            msg = pick.use(self.player, box)

        self.assertNotIn("durability", msg)
        self.assertEqual(pick.durability, 5)
        self.assertFalse(box.properties.get("locked"))
