"""Coverage for independently rolled procedural gem instances."""

from tests.fixtures import GameTestBase
from engine.items.gem_generator import GemGenerator, RARITY_TIERS


class TestGemGenerator(GameTestBase):
    def test_generated_gem_carries_type_size_and_quality_identity(self):
        gem = GemGenerator.generate_gem(self.world, level=8)

        self.assertIsNotNone(gem)
        self.assertFalse(gem.stackable)
        self.assertIn(gem.get_property("gem_rarity"), RARITY_TIERS)
        self.assertIn(gem.get_property("gem_size_score"), (1, 2, 3, 4, 5))
        self.assertIn(gem.get_property("gem_quality_score"), (1, 2, 3, 4, 5))
        self.assertEqual(gem.get_property("gem_quality_score"), gem.get_property("material_quality_score"))
        self.assertGreater(gem.value, 0)

    def test_gathering_grade_can_pin_the_gems_quality_but_not_its_size(self):
        gem = GemGenerator.generate_gem(
            self.world, level=1, template_id="item_rose_quartz", quality_score=5,
        )

        self.assertIsNotNone(gem)
        self.assertEqual("perfect", gem.get_property("gem_quality"))
        self.assertEqual(5, gem.get_property("material_quality_score"))
        self.assertTrue(gem.name.startswith("Perfect"))

    def test_explicit_template_rarity_overrides_legacy_value_inference(self):
        self.assertEqual("legendary", GemGenerator.template_rarity({"value": 1, "rarity": "legendary"}))
        self.assertEqual("common", GemGenerator.template_rarity({"value": 10}))
        self.assertEqual("rare", GemGenerator.template_rarity({"value": 200}))
