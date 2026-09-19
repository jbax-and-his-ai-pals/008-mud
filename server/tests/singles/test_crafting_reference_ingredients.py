# tests/singles/test_crafting_reference_ingredients.py
"""An ingredient may name a rule, not just a template.

`{"item_id": "item_x"}` still resolves exactly as it always did. What these
tests pin down is the newer half: `item_family` and `capability` references,
the `min_material_quality` floor that goes with them, and the single matcher
that counting, selecting, previewing and spending all share -- because a recipe
that *looks* craftable and then fails to craft is worse than one that says what
it is missing.
"""
from typing import Any, Dict
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.contracts import ContractRegistry
from engine.core.skill_system import SkillSystem
from engine.crafting.recipe import Recipe
from engine.items.item_factory import ItemFactory


CONTRACTS: Dict[str, Any] = {
    "schema_version": 1,
    "label": "Reference ingredient fixtures",
    "item_families": [
        {
            "id": "salvaged_part",
            "label": "salvaged part",
            "item_class": "Item",
            "capabilities": ["crafting_material", "generated_instance"],
            "generation_profile": "salvage",
        },
        {
            "id": "sealant",
            "label": "sealant",
            "item_class": "Item",
            "capabilities": ["crafting_material"],
        },
        {
            "id": "finished_goods",
            "label": "finished goods",
            "item_class": "Item",
            "capabilities": [],
        },
    ],
    "generation_profiles": [
        {
            "id": "salvage",
            "label": "Salvage",
            "item_family": "salvaged_part",
            "name_template": "{quality} {base}",
        },
    ],
}

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "item_good_panel": {
        "type": "Item",
        "name": "serviceable panel",
        "value": 4,
        "item_family": "salvaged_part",
        "generation_profile": "salvage",
    },
    "item_worn_panel": {
        "type": "Item",
        "name": "worn panel",
        "value": 2,
        "item_family": "salvaged_part",
        "generation_profile": "salvage",
    },
    "item_sealant_tube": {
        "type": "Item",
        "name": "sealant tube",
        "value": 3,
        "item_family": "sealant",
    },
    "item_shell": {
        "type": "Item",
        "name": "impact shell",
        "value": 20,
        "item_family": "finished_goods",
    },
}


class ReferenceIngredientTestBase(GameTestBase):
    """A world whose contracts come from this file, not from the content set."""

    def setUp(self):
        super().setUp()
        self.registry = ContractRegistry()
        self.registry.ingest(CONTRACTS)
        self.assertEqual([], list(self.registry.issues))
        self.world.contract_registry = self.registry
        self.manager = self.game.crafting_manager

        self._added_templates = []
        for item_id, template in TEMPLATES.items():
            if item_id not in self.world.item_templates:
                self._added_templates.append(item_id)
            self.world.item_templates[item_id] = dict(template)
        self.addCleanup(self._remove_templates)

    def _remove_templates(self):
        for item_id in self._added_templates:
            self.world.item_templates.pop(item_id, None)

    def give(self, item_id: str, quantity: int = 1, material_quality_score: int = 0):
        for _ in range(quantity):
            item = ItemFactory.create_item_from_template(item_id, self.world)
            self.assertIsNotNone(item, f"template '{item_id}' did not produce an item")
            item.properties["material_quality_score"] = material_quality_score
            item.stackable = False
            item.update_property("stackable", False)
            self.player.inventory.add_item(item)

    def recipe(self, ingredients) -> Recipe:
        return Recipe("reference_test", {
            "name": "Reference Test",
            "result_item_id": "item_shell",
            "result_quantity": 1,
            "ingredients": ingredients,
        })


class TestFamilyReference(ReferenceIngredientTestBase):

    def setUp(self):
        super().setUp()
        self.recipe_obj = self.recipe([{"item_family": "salvaged_part", "quantity": 2}])
        self.manager.recipes["reference_test"] = self.recipe_obj

    def test_a_family_reference_accepts_either_member(self):
        self.give("item_good_panel", 1, material_quality_score=2)
        self.give("item_worn_panel", 1, material_quality_score=2)
        can_craft, message = self.manager.can_craft(self.player, self.recipe_obj)
        self.assertTrue(can_craft, message)

    def test_a_family_reference_rejects_a_member_of_another_family(self):
        self.give("item_sealant_tube", 2, material_quality_score=5)
        can_craft, message = self.manager.can_craft(self.player, self.recipe_obj)
        self.assertFalse(can_craft)
        self.assertIn("salvaged part", message)

    def test_the_shortfall_message_names_the_family_and_the_grade_floor(self):
        recipe = self.recipe([{
            "item_family": "salvaged_part",
            "quantity": 2,
            "min_material_quality": 3,
        }])
        can_craft, message = self.manager.can_craft(self.player, recipe)
        self.assertFalse(can_craft)
        self.assertIn("salvaged part", message)
        self.assertIn("grade 3+", message)

    def test_a_grade_floor_is_enforced_against_the_item_not_the_family(self):
        self.give("item_worn_panel", 2, material_quality_score=1)
        self.give("item_good_panel", 1, material_quality_score=4)
        recipe = self.recipe([{
            "item_family": "salvaged_part",
            "quantity": 2,
            "min_material_quality": 3,
        }])
        can_craft, message = self.manager.can_craft(self.player, recipe)
        self.assertFalse(can_craft, message)

        self.give("item_good_panel", 1, material_quality_score=4)
        can_craft, message = self.manager.can_craft(self.player, recipe)
        self.assertTrue(can_craft, message)

    def test_counting_reports_only_units_that_satisfy_the_reference(self):
        self.give("item_good_panel", 3, material_quality_score=4)
        self.give("item_sealant_tube", 5, material_quality_score=4)
        ingredient = {"item_family": "salvaged_part", "quantity": 2}
        self.assertEqual(3, self.manager.count_ingredient(self.player, ingredient))

    def test_selection_prefers_the_higher_grade_within_one_reference(self):
        self.give("item_worn_panel", 1, material_quality_score=1)
        self.give("item_good_panel", 1, material_quality_score=4)
        selected = self.manager.select_recipe_ingredients(self.player, self.recipe_obj)
        self.assertIsNotNone(selected)
        self.assertEqual(
            ["item_good_panel", "item_worn_panel"],
            [item.obj_id for item in selected],
        )

    def test_quality_score_uses_the_selected_units_grade(self):
        self.give("item_good_panel", 2, material_quality_score=4)
        selected = self.manager.select_recipe_ingredients(self.player, self.recipe_obj)
        self.assertEqual(4, self.manager.ingredient_quality_score(self.player, self.recipe_obj, selected))

    def test_crafting_spends_the_units_the_matcher_accepted(self):
        self.give("item_good_panel", 2, material_quality_score=4)
        # The skill check is not what this test is about, and its roll is random.
        with patch.object(SkillSystem, "attempt_check", return_value=(True, "Success")):
            result = self.manager.craft(self.player, "reference_test")
        self.assertIn("Successfully crafted", result)
        self.assertEqual(0, self.player.inventory.count_item("item_good_panel"))
        self.assertEqual(1, self.player.inventory.count_item("item_shell"))


class TestCapabilityReference(ReferenceIngredientTestBase):

    def test_a_capability_reference_accepts_every_family_that_declares_it(self):
        recipe = self.recipe([{"capability": "crafting_material", "quantity": 2}])
        self.give("item_good_panel", 1, material_quality_score=1)
        self.give("item_sealant_tube", 1, material_quality_score=1)
        can_craft, message = self.manager.can_craft(self.player, recipe)
        self.assertTrue(can_craft, message)

    def test_a_capability_reference_rejects_a_family_that_does_not_declare_it(self):
        recipe = self.recipe([{"capability": "crafting_material", "quantity": 1}])
        self.give("item_shell", 1, material_quality_score=5)
        can_craft, _message = self.manager.can_craft(self.player, recipe)
        self.assertFalse(can_craft)

    def test_an_unknown_capability_matches_nothing_rather_than_everything(self):
        recipe = self.recipe([{"capability": "unheard_of", "quantity": 1}])
        self.give("item_good_panel", 4, material_quality_score=5)
        can_craft, _message = self.manager.can_craft(self.player, recipe)
        self.assertFalse(can_craft)

    def test_a_family_with_no_capabilities_is_never_matched_by_one(self):
        recipe = self.recipe([{"capability": "crafting_material", "quantity": 1}])
        self.give("item_shell", 1, material_quality_score=5)
        selected = self.manager.select_recipe_ingredients(self.player, recipe)
        self.assertIsNone(selected)


class TestReferencePrecedence(ReferenceIngredientTestBase):

    def test_item_id_still_wins_when_a_family_is_also_named(self):
        recipe = self.recipe([{
            "item_id": "item_good_panel",
            "item_family": "salvaged_part",
            "quantity": 1,
        }])
        self.give("item_worn_panel", 1, material_quality_score=5)
        can_craft, _message = self.manager.can_craft(self.player, recipe)
        self.assertFalse(can_craft, "item_id must win; the family reference is ignored")

        self.give("item_good_panel", 1, material_quality_score=5)
        can_craft, message = self.manager.can_craft(self.player, recipe)
        self.assertTrue(can_craft, message)

    def test_an_alternative_may_be_a_family(self):
        recipe = self.recipe([{
            "item_id": "item_sealant_tube",
            "quantity": 1,
            "alternatives": [{"item_family": "salvaged_part", "min_material_quality": 2}],
        }])
        self.give("item_good_panel", 1, material_quality_score=2)
        can_craft, message = self.manager.can_craft(self.player, recipe)
        self.assertTrue(can_craft, message)

    def test_an_alternative_family_grade_floor_is_honoured(self):
        recipe = self.recipe([{
            "item_id": "item_sealant_tube",
            "quantity": 1,
            "alternatives": [{"item_family": "salvaged_part", "min_material_quality": 3}],
        }])
        self.give("item_worn_panel", 1, material_quality_score=1)
        can_craft, _message = self.manager.can_craft(self.player, recipe)
        self.assertFalse(can_craft)

    def test_an_ingredient_naming_nothing_matches_nothing(self):
        recipe = self.recipe([{"quantity": 1}])
        self.give("item_good_panel", 4, material_quality_score=5)
        can_craft, _message = self.manager.can_craft(self.player, recipe)
        self.assertFalse(can_craft)

    def test_a_template_reference_does_not_read_a_grade_floor(self):
        """`item_id` wins, and the floor is a rule about a *set* of items.

        Naming one exact thing already answers "which item"; a floor beside it
        would be a second answer to the same question, so the engine ignores it
        rather than guessing which one the author meant. The editor keeps it
        from being authored in the first place.
        """
        recipe = self.recipe([{
            "item_id": "item_worn_panel",
            "quantity": 1,
            "min_material_quality": 9,
        }])
        self.give("item_worn_panel", 1, material_quality_score=0)
        can_craft, message = self.manager.can_craft(self.player, recipe)
        self.assertTrue(can_craft, message)


class TestReferenceResolutionForTooling(ReferenceIngredientTestBase):
    """`givemats` has to hand over something the recipe will accept."""

    def test_resolves_an_exact_template_to_itself(self):
        ingredient = {"item_id": "item_good_panel"}
        self.assertEqual("item_good_panel", self.manager.resolve_reference_template(ingredient))

    def test_resolves_a_family_to_a_member_template(self):
        ingredient = {"item_family": "sealant"}
        self.assertEqual("item_sealant_tube", self.manager.resolve_reference_template(ingredient))

    def test_resolves_a_capability_to_a_family_that_declares_it(self):
        ingredient = {"capability": "crafting_material"}
        resolved = self.manager.resolve_reference_template(ingredient)
        self.assertIn(resolved, {"item_good_panel", "item_worn_panel", "item_sealant_tube"})

    def test_resolves_nothing_when_no_template_matches(self):
        self.assertIsNone(self.manager.resolve_reference_template({"capability": "unheard_of"}))
        self.assertIsNone(self.manager.resolve_reference_template({"item_family": "absent"}))
        self.assertIsNone(self.manager.resolve_reference_template({"quantity": 1}))


class TestDescribeReference(ReferenceIngredientTestBase):

    def test_an_item_id_is_described_by_its_template_name(self):
        self.assertEqual("sealant tube", Recipe.describe_reference({"item_id": "item_sealant_tube"}, self.world))

    def test_a_family_is_described_by_its_contract_label(self):
        self.assertEqual("salvaged part", Recipe.describe_reference({"item_family": "salvaged_part"}, self.world))

    def test_an_undeclared_family_falls_back_to_its_own_id(self):
        self.assertEqual("absent", Recipe.describe_reference({"item_family": "absent"}, self.world))

    def test_a_capability_is_described_in_words(self):
        self.assertEqual(
            "crafting material",
            Recipe.describe_reference({"capability": "crafting_material"}, self.world),
        )

    def test_a_grade_floor_is_stated_only_when_it_bites(self):
        self.assertEqual(
            "salvaged part (grade 2+)",
            Recipe.describe_reference({"item_family": "salvaged_part", "min_material_quality": 2}, self.world),
        )
        self.assertEqual(
            "salvaged part",
            Recipe.describe_reference({"item_family": "salvaged_part", "min_material_quality": 0}, self.world),
        )

    def test_reference_labels_name_the_kind(self):
        self.assertEqual("item_id", Recipe.reference_label({"item_id": "x"}))
        self.assertEqual("item_family", Recipe.reference_label({"item_family": "x"}))
        self.assertEqual("capability", Recipe.reference_label({"capability": "x"}))
        self.assertEqual("", Recipe.reference_label({"quantity": 1}))
