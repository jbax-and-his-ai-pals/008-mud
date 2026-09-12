# tests/singles/test_combat_crafting_materials.py
"""Coverage for the combat-derived crafting slice: item_wolf_pelt,
item_wolf_fang, and item_troll_hide were already dropping from existing
hostile loot tables (dire_wolf, troll) with zero recipes consuming
them -- the same "authored but orphaned" shape this session already
closed for fishing and the gem ledger. These three new recipes close
it for combat materials.

None of the three set an explicit `difficulty: 0` (matching
stitch_leather_cap/forge_iron_sword's own un-guaranteed convention, not
the guaranteed-beginner commissions), so a real crafting-skill check
applies -- tests patch it the same way test_crafting_advanced_logic.py
and test_crafting_manager_full.py already do."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory


class TestCombatCraftingRecipes(GameTestBase):
    def _give(self, item_id, quantity=1):
        for _ in range(quantity):
            item = ItemFactory.create_item_from_template(item_id, self.world)
            self.player.inventory.add_item(item)

    def test_wolf_pelt_cloak_crafts_from_orphaned_materials(self):
        self._give("item_wolf_pelt", 2)
        self._give("item_leather_strip", 1)
        with patch("engine.crafting.crafting_manager.SkillSystem.attempt_check", return_value=(True, "Success!")):
            result = self.game.process_command("craft stitch_wolf_pelt_cloak")
        self.assertIn("craft", result.lower())
        cloak = self.player.inventory.find_item_by_name("wolf pelt cloak")
        self.assertIsNotNone(cloak)
        self.assertEqual(["body"], cloak.get_property("equip_slot"))
        self.assertGreater(cloak.get_property("defense"), 0)

    def test_wolf_fang_necklace_crafts_as_a_gift_item(self):
        self._give("item_wolf_fang", 2)
        with patch("engine.crafting.crafting_manager.SkillSystem.attempt_check", return_value=(True, "Success!")):
            result = self.game.process_command("craft string_wolf_fang_necklace")
        self.assertIn("craft", result.lower())
        necklace = self.player.inventory.find_item_by_name("wolf fang necklace")
        self.assertIsNotNone(necklace)
        self.assertEqual("gift", necklace.get_property("category"))

    def test_trollhide_vest_crafts_from_orphaned_troll_hide(self):
        self._give("item_troll_hide", 2)
        self._give("item_leather_strip", 1)
        with patch("engine.crafting.crafting_manager.SkillSystem.attempt_check", return_value=(True, "Success!")):
            result = self.game.process_command("craft cure_trollhide_vest")
        self.assertIn("craft", result.lower())
        vest = self.player.inventory.find_item_by_name("trollhide vest")
        self.assertIsNotNone(vest)
        self.assertEqual(["body"], vest.get_property("equip_slot"))
        self.assertGreater(vest.get_property("defense"), 2)

    def test_missing_ingredients_fails_cleanly(self):
        result = self.game.process_command("craft stitch_wolf_pelt_cloak")
        self.assertIsNone(self.player.inventory.find_item_by_name("wolf pelt cloak"))
        self.assertIn("missing ingredient", result.lower())
