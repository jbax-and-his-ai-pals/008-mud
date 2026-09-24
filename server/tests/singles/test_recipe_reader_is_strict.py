# tests/singles/test_recipe_reader_is_strict.py
"""A recipe that cannot be read is refused, by name, instead of misread.

`Recipe` was the only reader of a recipe and the content-set validator checked
almost nothing about one, so lenient reading here had no second line of defence.
Three shipped-shaped mistakes went through it in silence:

* `min_crafts: 3.0` -- the quality tier was filtered out of the list, so the
  craft reported no quality at all;
* `requires_discovery: "false"` -- `bool("false")` is True, so the recipe became
  permanently unlearnable;
* `result_quantity: "2"` -- `"2" * 3` is `"222"`, so a batch craft produced six
  items from one recipe.

Every one of those is now a refusal naming the field in the file's own terms.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.crafting.recipe import Recipe
from engine.utils.content_values import ContentValueError


class TestTheReaderRefusesWhatItCannotUse(unittest.TestCase):
    def build(self, **overrides):
        data = {"name": "Probe", "result_item_id": "item_x"}
        data.update(overrides)
        return Recipe("probe", data)

    def refuse(self, **overrides) -> str:
        with self.assertRaises(ContentValueError) as raised:
            self.build(**overrides)
        return str(raised.exception)

    def test_a_quoted_count_is_refused_rather_than_multiplied_as_a_string(self):
        message = self.refuse(result_quantity="2")
        self.assertIn("recipes.probe.result_quantity", message)
        self.assertIn("'2'", message)

    def test_a_null_count_is_refused_rather_than_kept_as_none(self):
        message = self.refuse(result_quantity=None)
        self.assertIn("recipes.probe.result_quantity", message)
        self.assertIn("null", message)

    def test_a_zero_result_quantity_is_refused(self):
        self.assertIn("at least 1", self.refuse(result_quantity=0))

    def test_a_string_switch_is_refused_rather_than_read_as_true(self):
        message = self.refuse(requires_discovery="false")
        self.assertIn("requires_discovery", message)
        self.assertIn("true or false", message)

    def test_a_tier_whose_practice_gate_is_a_string_is_refused(self):
        message = self.refuse(quality_tiers=[{"id": "t", "min_crafts": "1"}])
        self.assertIn("quality_tiers[0].min_crafts", message)

    def test_a_tier_whose_practice_gate_is_fractional_is_refused(self):
        """Truncating would invent a threshold the author did not write."""
        self.assertIn("quality_tiers[0].min_crafts", self.refuse(quality_tiers=[{"id": "t", "min_crafts": 1.5}]))

    def test_a_tier_with_no_practice_gate_is_refused(self):
        self.assertIn("min_crafts", self.refuse(quality_tiers=[{"id": "t"}]))

    def test_a_milestone_whose_count_is_a_string_is_refused(self):
        message = self.refuse(familiarity_milestones=[{"count": "3", "label": "L"}])
        self.assertIn("familiarity_milestones[0].count", message)

    def test_ingredients_that_are_an_object_are_refused(self):
        """It used to be kept as-is and iterated as its keys."""
        self.assertIn("ingredients must be a list", self.refuse(ingredients={"item_id": "i"}))

    def test_an_ingredient_that_is_not_an_object_is_refused(self):
        self.assertIn("ingredients[0]", self.refuse(ingredients=["item_i"]))

    def test_aliases_that_are_a_string_are_refused(self):
        self.assertIn("aliases must be a list", self.refuse(aliases="posy"))

    def test_an_empty_alias_is_refused(self):
        # By index, so the author knows which one in the list is the problem.
        self.assertIn("aliases[1]", self.refuse(aliases=["posy", "  "]))

    def test_a_quoted_difficulty_is_refused(self):
        self.assertIn("difficulty", self.refuse(difficulty="7"))

    def test_a_recipe_that_is_not_an_object_is_refused(self):
        with self.assertRaises(ContentValueError):
            Recipe("probe", "not an object")  # type: ignore[arg-type]


class TestWholeFloatsAreReadNotRefused(unittest.TestCase):
    """`3.0` is what a JSON writer with one number type produces."""

    def test_a_whole_float_count_is_read_as_that_integer(self):
        recipe = Recipe("probe", {
            "result_item_id": "item_x",
            "result_quantity": 2.0,
            "quality_tiers": [{"id": "t", "min_crafts": 3.0, "min_material_quality": 2.0}],
            "familiarity_milestones": [{"count": 1.0, "label": "L"}],
        })
        self.assertEqual(2, recipe.result_quantity)
        self.assertEqual(1, len(recipe.quality_tiers))
        self.assertEqual(3, recipe.quality_tiers[0]["min_crafts"])
        self.assertEqual(2, recipe.quality_tiers[0]["min_material_quality"])
        self.assertEqual(1, recipe.familiarity_milestones[0]["count"])

    def test_a_whole_float_difficulty_is_read(self):
        self.assertEqual(0, Recipe("probe", {"result_item_id": "item_x", "difficulty": 0.0}).difficulty)


class TestAbsentFieldsKeepTheirDefaults(unittest.TestCase):
    """Being strict about wrong values is not the same as requiring every field."""

    def test_a_recipe_with_only_its_result_loads(self):
        recipe = Recipe("probe", {"result_item_id": "item_x"})
        self.assertEqual(1, recipe.result_quantity)
        self.assertFalse(recipe.requires_discovery)
        self.assertIsNone(recipe.difficulty)
        self.assertIsNone(recipe.station_required)
        self.assertEqual([], recipe.ingredients)
        self.assertEqual([], recipe.aliases)
        self.assertEqual([], recipe.quality_tiers)
        self.assertEqual([], recipe.familiarity_milestones)

    def test_an_explicit_null_station_is_handcrafting(self):
        self.assertIsNone(Recipe("probe", {"result_item_id": "item_x", "station_required": None}).station_required)

    def test_a_tier_without_the_optional_gates_is_kept(self):
        recipe = Recipe("probe", {"result_item_id": "item_x", "quality_tiers": [{"id": "t", "min_crafts": 1}]})
        self.assertEqual(1, len(recipe.quality_tiers))


class TestTheLoadersSkipOneRecipeNotTheFile(unittest.TestCase):
    """One unusable recipe used to be able to take a whole file with it."""

    def setUp(self):
        from tests.fixtures import GameTestBase  # noqa: F401 - documents the fixture used

    def test_a_refused_recipe_leaves_its_neighbours_loaded(self):
        import tempfile

        from engine.crafting.crafting_manager import CraftingManager
        from tests.fixtures import FANTASY_FRONTIER
        from engine.world.world import World
        from engine.server.content_set import load_content_set

        content_set, issues = load_content_set(FANTASY_FRONTIER)
        self.assertIsNotNone(content_set)
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        data_root = scratch / "data"
        (data_root / "crafting").mkdir(parents=True)
        (data_root / "crafting" / "recipes.json").write_text(json.dumps({
            "_comment": "notes are not recipes",
            "good_recipe": {"name": "Good", "result_item_id": "item_x", "result_quantity": 1},
            "bad_recipe": {"name": "Bad", "result_item_id": "item_x", "result_quantity": "2"},
            "also_good": {"name": "Also Good", "result_item_id": "item_x"},
        }), encoding="utf-8")

        world = World(content_set=content_set, save_directory=str(scratch))
        world.content_root = str(data_root)
        manager = CraftingManager(world)
        self.assertEqual({"good_recipe", "also_good"}, set(manager.recipes))
        self.assertEqual(1, len(manager.recipe_errors))
        self.assertIn("bad_recipe.result_quantity", manager.recipe_errors[0])


class TestTheValidatorAsksTheSameReader(unittest.TestCase):
    """So the two cannot drift the way `min_crafts` drifted."""

    def _package_with_recipe(self, recipe: dict) -> Path:
        from engine.server.content_set import load_content_set  # noqa: F401 - documents the API used

        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        package = scratch / "content_set"
        for directory in ("items", "regions", "npcs", "crafting", "contracts"):
            (package / "data" / directory).mkdir(parents=True)
        (package / "rules").mkdir(parents=True)
        (package / "presentation").mkdir(parents=True)
        (package / "content_set.manifest.json").write_text(json.dumps({
            "id": "recipe_probe", "title": "Recipe Probe", "version": "0.1.0",
            "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
            "paths": {
                "content_root": "data", "ruleset": "rules/ruleset.json",
                "presentation": "presentation/default.json",
            },
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": ["inventory", "crafting"],
        }), encoding="utf-8")
        (package / "rules" / "ruleset.json").write_text(json.dumps({}), encoding="utf-8")
        (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
        (package / "data" / "regions" / "town.json").write_text(json.dumps({
            "region_id": "town", "rooms": {"square": {"name": "Square", "exits": {}}},
        }), encoding="utf-8")
        (package / "data" / "items" / "items.json").write_text(json.dumps({
            "item_shell": {"type": "Item", "name": "shell"},
        }), encoding="utf-8")
        (package / "data" / "crafting" / "recipes.json").write_text(
            json.dumps({"probe_recipe": recipe}), encoding="utf-8",
        )
        return package

    def _errors(self, recipe: dict) -> list:
        from engine.server.content_set import load_content_set

        _definition, issues = load_content_set(self._package_with_recipe(recipe))
        return [issue.message for issue in issues if issue.severity == "error"]

    def test_a_string_min_crafts_fails_the_build(self):
        """The exact gap: the validator used to accept this and the engine drop the tier."""
        errors = self._errors({
            "name": "Probe", "result_item_id": "item_shell",
            "quality_tiers": [{"id": "field", "min_crafts": "1", "value_multiplier": 1.0}],
        })
        self.assertTrue(
            any("min_crafts" in message and "integer" in message for message in errors), errors,
        )

    def test_a_string_requires_discovery_fails_the_build(self):
        errors = self._errors({"name": "Probe", "result_item_id": "item_shell", "requires_discovery": "false"})
        self.assertTrue(any("requires_discovery" in message for message in errors), errors)

    def test_a_recipe_that_is_not_an_object_fails_the_build(self):
        from engine.server.content_set import load_content_set

        package = self._package_with_recipe({"name": "Probe", "result_item_id": "item_shell"})
        (package / "data" / "crafting" / "recipes.json").write_text(
            json.dumps({"probe_recipe": "not an object"}), encoding="utf-8",
        )
        _definition, issues = load_content_set(package)
        errors = [issue.message for issue in issues if issue.severity == "error"]
        self.assertTrue(any("must be an object" in message for message in errors), errors)

    def test_a_well_formed_recipe_still_passes(self):
        self.assertEqual([], self._errors({
            "name": "Probe", "result_item_id": "item_shell", "result_quantity": 1,
            "difficulty": 0, "aliases": ["shell"],
            "ingredients": [{"item_id": "item_shell", "quantity": 1}],
            "quality_tiers": [{"id": "t", "min_crafts": 1, "min_material_quality": 0}],
            "familiarity_milestones": [{"count": 1, "label": "L"}],
        }))

    def test_every_shipped_content_set_still_passes(self):
        from engine.server.content_set import load_content_set

        for name in ("fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage"):
            _definition, issues = load_content_set(REPO_ROOT / "content_sets" / name)
            errors = [issue.message for issue in issues if issue.severity == "error"]
            self.assertEqual([], errors, name)


if __name__ == "__main__":
    unittest.main()
