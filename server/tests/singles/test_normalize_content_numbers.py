# tests/singles/test_normalize_content_numbers.py
"""Whole-number floats in fields the engine means as integers.

The bug this exists for: the world editor's GDScript `JSON.stringify` writes
every number as a float, so one editor save turned 2,058 values in
`fantasy_frontier` into `2.0`. Python's `isinstance(2.0, int)` is False, so the
content validator rejected ingredient quantities, region level bands, vendor
order prices, quest stage indexes and material grades -- fields nobody edited --
and every test that never read those fields kept passing.

The normaliser's rule is deliberately narrow: a whole float becomes an int only
where the schema (contracts) or the validator's own type checks (entity files)
say the field is an integer. Everything these tests assert follows from that.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_tool():
    path = REPO_ROOT / "toolkit" / "normalize_content_numbers.py"
    spec = importlib.util.spec_from_file_location("normalize_content_numbers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


class TestTheConversionRule(unittest.TestCase):
    def normalize(self, payload):
        item, changed = tool.normalize_document(payload, {}, is_contracts=False)
        return item, changed

    def test_a_whole_float_in_an_integer_field_becomes_an_int(self):
        result, changed = self.normalize({"ingredients": [{"quantity": 2.0}]})
        self.assertEqual(1, changed)
        self.assertIsInstance(result["ingredients"][0]["quantity"], int)
        self.assertEqual(2, result["ingredients"][0]["quantity"])

    def test_a_fractional_float_in_an_integer_field_is_left_alone(self):
        """Truncating would be inventing a value the author did not write."""
        result, changed = self.normalize({"ingredients": [{"quantity": 2.5}]})
        self.assertEqual(0, changed)
        self.assertEqual(2.5, result["ingredients"][0]["quantity"])

    def test_a_float_field_keeps_its_float(self):
        """`weight` is read as a float; 3.0 there is legitimate and untouched."""
        result, changed = self.normalize({"weight": 3.0, "chance": 1.0})
        self.assertEqual(0, changed)
        self.assertIsInstance(result["weight"], float)

    def test_a_nested_context_field_is_converted(self):
        """A region's band is `properties.level_band.min`, however deep it sits."""
        result, changed = self.normalize({"properties": {"level_band": {"min": 2.0, "max": 4.0}}})
        self.assertEqual(2, changed)
        self.assertEqual({"min": 2, "max": 4}, result["properties"]["level_band"])

    def test_a_vector_context_field_is_converted_element_wise(self):
        result, changed = self.normalize({"spawner": {"level_range": [1.0, 3.0]}})
        self.assertEqual(2, changed)
        self.assertEqual([1, 3], result["spawner"]["level_range"])

    def test_a_bare_float_outside_any_rule_is_left_alone(self):
        result, changed = self.normalize({"mystery": 7.0})
        self.assertEqual(0, changed)
        self.assertIsInstance(result["mystery"], float)

    def test_booleans_are_not_numbers(self):
        result, changed = self.normalize({"repeatable": True})
        self.assertEqual(0, changed)
        self.assertIs(result["repeatable"], True)


class TestTheContractRule(unittest.TestCase):
    def test_a_schema_int_field_is_converted(self):
        from engine.contracts.registry import CONTRACT_SCHEMAS

        payload = {"generation_profiles": [{
            "id": "p", "item_family": "f",
            "rarity_tiers": [{"id": "common", "score": 1.0, "weight": 80.0, "rank": 1.0}],
        }]}
        result, changed = tool.normalize_document(payload, CONTRACT_SCHEMAS, is_contracts=True)
        tier = result["generation_profiles"][0]["rarity_tiers"][0]
        self.assertEqual(2, changed, "`score` and `rank` are ints; `weight` is a float")
        self.assertIsInstance(tier["score"], int)
        self.assertIsInstance(tier["rank"], int)
        self.assertIsInstance(tier["weight"], float)


class TestTheRuleIsMeasuredNotGuessed(unittest.TestCase):
    """Every name the rule converts appears *only* as a whole number in content.

    This is the test that would have caught the first version of the rule, which
    knew about the fields the content-set validator checks and not the ones only
    the engine reads. `min_crafts` was the one that bit: `Recipe` accepts a
    quality tier only when `min_crafts` is an int, so a float there silently
    dropped every tier a recipe authored and the craft reported no quality at
    all -- with the validator perfectly happy.
    """

    def _value_kinds(self):
        from collections import Counter

        whole, fractional = Counter(), Counter()

        def walk(value, key=None):
            if isinstance(value, float):
                (whole if value.is_integer() else fractional)[key] += 1
            elif isinstance(value, dict):
                for child_key, child in value.items():
                    walk(child, str(child_key))
            elif isinstance(value, list):
                for entry in value:
                    walk(entry, key)

        for content_set in TestOnRealContent.SETS:
            for path in tool.content_json_files(REPO_ROOT / "content_sets" / content_set):
                try:
                    walk(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    continue
        return whole, fractional

    def test_no_rule_field_is_also_a_fractional_field(self):
        _whole, fractional = self._value_kinds()
        offenders = sorted(
            name for name in tool.INT_FIELDS_ANYWHERE
            if name in fractional and name not in ("min", "max")
        )
        self.assertEqual(
            [], offenders,
            "these names appear with a fractional value too, so converting them "
            "is a judgement call rather than a rule: %s" % offenders,
        )

    def test_every_float_field_the_engine_reads_as_an_integer_is_covered(self):
        """A recipe's quality tiers are the case that proved this matters."""
        payload = {"r": {"quality_tiers": [{"id": "t", "min_crafts": 5.0, "rank": 2.0}]}}
        result, changed = tool.normalize_document(payload, {}, is_contracts=False)
        tier = result["r"]["quality_tiers"][0]
        self.assertEqual(2, changed)
        self.assertIsInstance(tier["min_crafts"], int)
        self.assertIsInstance(tier["rank"], int)

    def test_a_recipe_tier_whose_practice_gate_is_a_float_is_refused(self):
        """The reader refuses a fractional gate, and that is why the normaliser exists.

        `2.0` means two and is read as two; `2.5` is refused rather than
        truncated. A whole float is what a JSON writer with one number type
        produces, so normalising it is a repair; a fraction is an authoring
        mistake the reader should not paper over.
        """
        from engine.crafting.recipe import Recipe
        from engine.utils.content_values import ContentValueError

        with self.assertRaises(ContentValueError) as raised:
            Recipe("probe", {
                "name": "Probe",
                "quality_tiers": [{"id": "fine", "label": "Fine", "min_crafts": 2.5, "value_multiplier": 1.5}],
            })
        self.assertIn("min_crafts", str(raised.exception))

    def test_a_whole_float_gate_is_read_rather_than_dropped(self):
        from engine.crafting.recipe import Recipe

        recipe = Recipe("probe", {
            "name": "Probe",
            "quality_tiers": [{"id": "fine", "label": "Fine", "min_crafts": 1.0, "value_multiplier": 1.5}],
        })
        self.assertEqual(1, len(recipe.quality_tiers))
        self.assertEqual(1, recipe.quality_tiers[0]["min_crafts"])


class TestOnRealContent(unittest.TestCase):
    SETS = ("fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage")

    def test_every_shipped_content_set_is_already_normalized(self):
        """The gate `run_content_checks.py` runs, asserted here as well.

        A shipped set that needs this tool run on it is a set whose authored
        integers are floats, which means the editor wrote it.
        """
        for content_set in self.SETS:
            total, touched = tool.normalize_content_set(REPO_ROOT / "content_sets" / content_set)
            self.assertEqual(0, total, "%s needs normalising: %s" % (content_set, touched))

    def test_normalising_is_idempotent(self):
        for content_set in self.SETS:
            root = REPO_ROOT / "content_sets" / content_set
            first, _ = tool.normalize_content_set(root)
            second, _ = tool.normalize_content_set(root)
            self.assertEqual(0, first)
            self.assertEqual(0, second)


class TestItRewritesOnlyWhatMoved(unittest.TestCase):
    def test_apply_rewrites_a_dirty_file_and_leaves_a_clean_one_alone(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "sample_set"
            (root / "data" / "items").mkdir(parents=True)
            (root / "content_set.manifest.json").write_text("{}", encoding="utf-8")
            dirty = root / "data" / "items" / "dirty.json"
            dirty.write_text(json.dumps({"box": {"properties": {"salvage_output": {}}}}), encoding="utf-8")
            clean = root / "data" / "items" / "clean.json"
            clean.write_text(json.dumps({"recipe": {"ingredients": [{"quantity": 2, "weight": 0.5}]}}), encoding="utf-8")

            before = clean.stat().st_mtime_ns
            total, touched = tool.normalize_content_set(root, apply=True)
            self.assertEqual(0, total, "this fixture has nothing to convert")
            self.assertEqual([], touched)
            self.assertEqual(before, clean.stat().st_mtime_ns, "a clean file must not be rewritten")

    def test_apply_converts_and_reports_the_file(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "sample_set"
            (root / "data" / "crafting").mkdir(parents=True)
            (root / "content_set.manifest.json").write_text("{}", encoding="utf-8")
            path = root / "data" / "crafting" / "recipes.json"
            path.write_text(json.dumps({"r": {"ingredients": [{"quantity": 3.0}]}}), encoding="utf-8")

            total, touched = tool.normalize_content_set(root, apply=True)
            self.assertEqual(1, total)
            self.assertEqual(["data/crafting/recipes.json (1)"], touched)
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(written["r"]["ingredients"][0]["quantity"], int)

    def test_editor_state_is_never_touched(self):
        """Layout coordinates in `editor/` are genuinely fractional."""
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "sample_set"
            (root / "editor").mkdir(parents=True)
            (root / "content_set.manifest.json").write_text("{}", encoding="utf-8")
            layout = root / "editor" / "quest_layout.json"
            layout.write_text(json.dumps({"quests": {"q": {"stage_index": 0.0, "x": 12.0}}}), encoding="utf-8")

            total, touched = tool.normalize_content_set(root, apply=True)
            self.assertEqual(0, total)
            self.assertEqual([], touched)
            self.assertIsInstance(json.loads(layout.read_text(encoding="utf-8"))["quests"]["q"]["stage_index"], float)


if __name__ == "__main__":
    unittest.main()
