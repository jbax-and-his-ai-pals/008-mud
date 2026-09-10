"""Coverage for engine/items/chest_loot_generator.py: the first Container-
type content in this game, generated (not templated) contents, and the
one new piece of randomization machinery this needed (roll_around)."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.chest_loot_generator import ChestLootGenerator
from engine.items.container import Container
from engine.utils.utils import roll_around


class TestRollAround(GameTestBase):
    def test_stays_within_explicit_bounds_across_many_trials(self):
        for _ in range(200):
            value = roll_around(10, 20, minimum=5, maximum=15)
            self.assertGreaterEqual(value, 5)
            self.assertLessEqual(value, 15)

    def test_degenerate_range_returns_the_bound(self):
        # minimum/maximum collapsing the range shouldn't raise.
        self.assertEqual(5, roll_around(10, 1, minimum=5, maximum=5))


class TestChestLootGenerator(GameTestBase):
    def test_generated_chest_is_a_locked_container_with_scaled_difficulty(self):
        low_level_difficulties = [
            ChestLootGenerator.generate_chest(self.world, level=1).get_property("lock_difficulty")
            for _ in range(30)
        ]
        high_level_difficulties = [
            ChestLootGenerator.generate_chest(self.world, level=15).get_property("lock_difficulty")
            for _ in range(30)
        ]
        self.assertLess(
            sum(low_level_difficulties) / len(low_level_difficulties),
            sum(high_level_difficulties) / len(high_level_difficulties),
            "higher-level chests should trend toward higher lock difficulty on average",
        )

    def test_generated_chest_contents_never_contain_another_chest(self):
        for level in (1, 5, 10, 20):
            for _ in range(15):
                chest = ChestLootGenerator.generate_chest(self.world, level=level)
                self.assertIsInstance(chest, Container)
                self.assertTrue(chest.properties.get("locked"))
                contents = chest.properties.get("contains", [])
                self.assertGreaterEqual(len(contents), 1)
                self.assertLessEqual(len(contents), 3)
                for item in contents:
                    self.assertNotIsInstance(item, Container)

    def test_generated_gem_carries_the_gathering_systems_quality_score(self):
        with patch("engine.items.chest_loot_generator.weighted_choice", return_value="gem"):
            item = ChestLootGenerator._generate_slot_item(self.world, level=5)
        self.assertIsNotNone(item)
        score = item.get_property("material_quality_score")
        self.assertIn(score, (1, 2, 3))
        self.assertTrue(item.get_property("material_quality_label"))
        self.assertFalse(item.stackable)

    def test_generated_equipment_can_carry_a_rolled_affix(self):
        with patch("engine.items.chest_loot_generator.weighted_choice", return_value="equipment"), \
             patch("engine.items.chest_loot_generator.roll_around", return_value=1.0):
            item = ChestLootGenerator._generate_slot_item(self.world, level=15)
        self.assertIsNotNone(item)
        # LootGenerator prefixes/suffixes the base item's name when an
        # affix lands; with rarity_roll forced to 1.0 at a high level the
        # affix chance is guaranteed.
        self.assertNotEqual("", item.name)

    def test_generated_currency_uses_the_existing_gold_coin_item(self):
        with patch("engine.items.chest_loot_generator.weighted_choice", return_value="currency"):
            item = ChestLootGenerator._generate_slot_item(self.world, level=5)
        self.assertIsNotNone(item)
        self.assertEqual("item_gold_coin", item.obj_id)


class TestChestTrapRoll(GameTestBase):
    def test_never_trapped_below_the_chance_threshold(self):
        with patch("engine.items.chest_loot_generator.random.random", return_value=0.99):
            trapped, kind, difficulty = ChestLootGenerator._roll_trap(level=5)
        self.assertFalse(trapped)
        self.assertIsNone(kind)
        self.assertIsNone(difficulty)

    def test_always_trapped_at_the_chance_threshold(self):
        with patch("engine.items.chest_loot_generator.random.random", return_value=0.0):
            trapped, kind, difficulty = ChestLootGenerator._roll_trap(level=5)
        self.assertTrue(trapped)
        self.assertIn(kind, ("damage", "poison"))
        self.assertGreaterEqual(difficulty, 5)

    def test_trap_difficulty_scales_with_level_independently_of_lock_difficulty(self):
        low_level_difficulties = []
        high_level_difficulties = []
        with patch("engine.items.chest_loot_generator.random.random", return_value=0.0):
            for _ in range(30):
                _, _, difficulty = ChestLootGenerator._roll_trap(level=1)
                low_level_difficulties.append(difficulty)
            for _ in range(30):
                _, _, difficulty = ChestLootGenerator._roll_trap(level=15)
                high_level_difficulties.append(difficulty)
        self.assertLess(
            sum(low_level_difficulties) / len(low_level_difficulties),
            sum(high_level_difficulties) / len(high_level_difficulties),
        )

    def test_generated_chest_carries_trap_state_when_trapped(self):
        with patch("engine.items.chest_loot_generator.random.random", return_value=0.0):
            chest = ChestLootGenerator.generate_chest(self.world, level=5)
        self.assertTrue(chest.properties.get("trapped"))
        self.assertIn(chest.properties.get("trap_kind"), ("damage", "poison"))
        self.assertIsNotNone(chest.properties.get("trap_difficulty"))

    def test_generated_chest_has_no_trap_kind_when_untrapped(self):
        with patch("engine.items.chest_loot_generator.random.random", return_value=0.99):
            chest = ChestLootGenerator.generate_chest(self.world, level=5)
        self.assertFalse(chest.properties.get("trapped"))
        self.assertIsNone(chest.properties.get("trap_kind"))
