# tests/singles/test_loot_generator_full.py
"""Coverage for engine/items/loot_generator.py's LootGenerator beyond what
test_batch_loot.py/test_batch_loot_lifecycle.py already exercise: missing
base template, existing template equip_effect merging, _pick_affix's
no-valid-candidates branch, and _apply_prefix's weight modifier."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.loot_generator import LootGenerator
from engine.items.affix_data import PREFIXES


class TestGenerateLootMissingTemplate(GameTestBase):
    def test_unknown_base_template_returns_none(self):
        result = LootGenerator.generate_loot("totally_bogus_template_xyz", self.world)
        self.assertIsNone(result)


class TestGenerateLootExistingEquipEffect(GameTestBase):
    def test_existing_stat_mod_effect_is_merged_with_suffix_stats(self):
        self.world.item_templates["test_ring"] = {
            "type": "Item", "name": "Ring", "value": 50, "weight": 0.1,
            "properties": {
                "equip_slot": ["ring"],
                "equip_effect": {"type": "stat_mod", "name": "Old Enchant", "modifiers": {"luck": 1}},
            },
        }
        with patch.object(LootGenerator, "_pick_affix") as mock_pick:
            # Prefix roll (random.random()=1.0) fails, so _pick_affix is only
            # ever called once, for the suffix roll (0.0, which passes).
            mock_pick.side_effect = [("of the Bear", {"equip_stats": {"strength": 2}, "value_mult": 1.0})]
            with patch("random.random", side_effect=[1.0, 0.0]):
                item = LootGenerator.generate_loot("test_ring", self.world, level=1)

        self.assertIsNotNone(item)
        effect = item.get_property("equip_effect")
        self.assertEqual(1, effect["modifiers"]["luck"])
        self.assertEqual(2, effect["modifiers"]["strength"])


class TestPickAffixNoValidCandidates(unittest.TestCase):
    def test_no_matching_type_or_level_returns_empty(self):
        name, data = LootGenerator._pick_affix(PREFIXES, "TotallyUnknownType", level=1)
        self.assertEqual("", name)
        self.assertEqual({}, data)


class TestApplyPrefixWeightModifier(GameTestBase):
    def test_heavy_prefix_increases_weight(self):
        self.world.item_templates["test_heavy_armor"] = {
            "type": "Armor", "name": "Plate", "value": 100, "weight": 5.0,
            "properties": {"defense": 5, "equip_slot": ["body"]},
        }
        with patch.object(LootGenerator, "_pick_affix") as mock_pick:
            mock_pick.side_effect = [("Heavy", PREFIXES["Heavy"]), ("", {})]
            with patch("random.random", side_effect=[0.0, 1.0]):
                item = LootGenerator.generate_loot("test_heavy_armor", self.world, level=1)

        self.assertIsNotNone(item)
        self.assertEqual(7.0, item.weight)
        self.assertEqual(7.0, item.get_property("weight"))


if __name__ == "__main__":
    unittest.main()
