import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestClassifyPolarity(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_positive_fields(self):
        for field_id in ("sanctity", "harmony", "vitality", "hope"):
            self.assertEqual("positive", self.server._classify_polarity(field_id))

    def test_neutral_fields(self):
        for field_id in ("fog", "entropy", "wild"):
            self.assertEqual("neutral", self.server._classify_polarity(field_id))

    def test_unrecognized_fields_default_to_negative(self):
        for field_id in ("blight", "corruption", "made_up_field"):
            self.assertEqual("negative", self.server._classify_polarity(field_id))


class TestInteractionCoefficient(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_explicit_rule_takes_precedence(self):
        self.server.field_interaction_rules = {"sanctity": {"blight": 0.9}}
        coefficient = self.server._interaction_coefficient("sanctity", "blight", fallback=0.1)
        self.assertEqual(0.9, coefficient)

    def test_explicit_rule_is_clamped_to_non_negative(self):
        self.server.field_interaction_rules = {"sanctity": {"blight": -0.5}}
        coefficient = self.server._interaction_coefficient("sanctity", "blight", fallback=0.1)
        self.assertEqual(0.0, coefficient)

    def test_positive_suppresses_negative_uses_fallback(self):
        self.server.field_interaction_rules = {}
        coefficient = self.server._interaction_coefficient("sanctity", "blight", fallback=0.6)
        self.assertEqual(0.6, coefficient)

    def test_non_positive_source_does_not_suppress(self):
        self.server.field_interaction_rules = {}
        coefficient = self.server._interaction_coefficient("blight", "sanctity", fallback=0.6)
        self.assertEqual(0.0, coefficient)

    def test_neutral_source_does_not_suppress(self):
        self.server.field_interaction_rules = {}
        coefficient = self.server._interaction_coefficient("fog", "blight", fallback=0.6)
        self.assertEqual(0.0, coefficient)


class TestApplyFieldInteractions(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_positive_field_damps_overlapping_negative_field_cell(self):
        blight = self.server._ensure_field("blight")
        sanctity = self.server._ensure_field("sanctity")
        blight.seed_cell(3, 3, 1.0)
        sanctity.seed_cell(3, 3, 1.0)
        self.server.field_interaction_rules = {"sanctity": {"blight": 0.6}}

        before = blight.snapshot().get("3,3", 0.0)
        deltas: dict = {}
        self.server._apply_field_interactions(deltas)
        after = blight.snapshot().get("3,3", 0.0)

        self.assertLess(after, before)
        self.assertIn("blight", deltas)

    def test_no_overlap_produces_no_deltas(self):
        blight = self.server._ensure_field("blight")
        sanctity = self.server._ensure_field("sanctity")
        blight.seed_cell(1, 1, 1.0)
        sanctity.seed_cell(7, 7, 1.0)  # different cell, no overlap
        self.server.field_interaction_rules = {"sanctity": {"blight": 0.6}}

        deltas: dict = {}
        self.server._apply_field_interactions(deltas)
        self.assertEqual({}, deltas)

    def test_zero_value_target_cells_are_skipped(self):
        blight = self.server._ensure_field("blight")
        self.server.fields["blight"] = blight
        deltas: dict = {}
        self.server._apply_field_interactions(deltas)  # no cells seeded anywhere
        self.assertEqual({}, deltas)


if __name__ == "__main__":
    unittest.main()
