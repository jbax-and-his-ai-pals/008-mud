# tests/singles/test_loot_distribution.py
import unittest
from engine.utils.utils import weighted_choice

class TestLootDistribution(unittest.TestCase):

    def test_weighted_choice_basic(self):
        """Verify weighted choice picks the only available option."""
        choices = {"gold": 100}
        result = weighted_choice(choices)
        self.assertEqual(result, "gold")

    def test_weighted_choice_zero_weight(self):
        """Verify options with 0 weight are never picked if alternatives exist."""
        choices = {"rare_item": 0, "junk": 100}
        # Run multiple times to ensure 0% really means 0%
        results = [weighted_choice(choices) for _ in range(50)]
        self.assertNotIn("rare_item", results)

    def test_weighted_choice_empty(self):
        """Verify empty choices return None."""
        self.assertIsNone(weighted_choice({}))

    def test_weighted_choice_negative_weights(self):
        """Verify negative weights are treated as 0 or handled gracefully."""
        choices = {"bad": -10, "good": 10}
        result = weighted_choice(choices)
        self.assertEqual(result, "good")