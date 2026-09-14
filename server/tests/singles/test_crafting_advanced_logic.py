# tests/singles/test_crafting_advanced_logic.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe

class TestCraftingAdvancedLogic(GameTestBase):

    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        
        # Define complex recipe: 2 Wood + 1 Iron -> 10 Arrows
        self.world.item_templates["item_wood"] = {"type": "Item", "name": "wood", "value": 1}
        self.world.item_templates["item_iron"] = {"type": "Item", "name": "iron", "value": 1}
        self.world.item_templates["item_arrow"] = {"type": "Item", "name": "arrow", "value": 1, "stackable": True}
        
        self.recipe = Recipe("bundle_arrows", {
            "name": "Bundle of Arrows",
            "result_item_id": "item_arrow",
            "result_quantity": 10,
            "ingredients": [
                {"item_id": "item_wood", "quantity": 2},
                {"item_id": "item_iron", "quantity": 1}
            ]
        })
        self.manager.recipes["bundle_arrows"] = self.recipe

    def test_multi_ingredient_consumption(self):
        """Verify multiple types of materials are consumed correctly."""
        # 1. Provide materials
        wood = ItemFactory.create_item_from_template("item_wood", self.world)
        iron = ItemFactory.create_item_from_template("item_iron", self.world)
        if wood and iron and self.player:
            self.player.inventory.add_item(wood, 2)
            self.player.inventory.add_item(iron, 1)
            
            # 2. Craft
            with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "Success")):
                self.manager.craft(self.player, "bundle_arrows")
                
            # 3. Assertions
            self.assertEqual(self.player.inventory.count_item("item_wood"), 0)
            self.assertEqual(self.player.inventory.count_item("item_iron"), 0)
            self.assertEqual(self.player.inventory.count_item("item_arrow"), 10)


class TestIngredientSubstitution(GameTestBase):
    """A recipe ingredient may declare `alternatives`: other item_ids that
    satisfy the same slot, each with its own quality_penalty -- the
    "substitutions with trade-offs" the gathering system already has an
    analogue of (herb bed / berry bramble)."""

    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        self.recipe = Recipe("sub_test_recipe", {
            "name": "Substitution Test Item",
            "result_item_id": "item_wildflower_posy",
            "result_quantity": 1,
            "ingredients": [
                {
                    "item_id": "item_wild_herbs",
                    "quantity": 2,
                    "alternatives": [{"item_id": "item_forest_berries", "quality_penalty": 1}],
                }
            ],
        })
        self.manager.recipes["sub_test_recipe"] = self.recipe

    def _give(self, item_id, quantity, material_quality_score=None):
        for _ in range(quantity):
            item = ItemFactory.create_item_from_template(item_id, self.world)
            if material_quality_score is not None:
                item.properties["material_quality_score"] = material_quality_score
                item.stackable = False
            self.player.inventory.add_item(item)

    def test_ingredient_options_lists_primary_then_alternatives(self):
        ingredient = self.recipe.ingredients[0]
        options = Recipe.ingredient_options(ingredient)
        self.assertEqual(
            [{"item_id": "item_wild_herbs", "quality_penalty": 0}, {"item_id": "item_forest_berries", "quality_penalty": 1}],
            options,
        )

    def test_ingredient_options_defaults_missing_alternative_penalty_to_zero(self):
        ingredient = {"item_id": "item_a", "alternatives": [{"item_id": "item_b"}]}
        options = Recipe.ingredient_options(ingredient)
        self.assertEqual(0, options[1]["quality_penalty"])

    def test_can_craft_succeeds_with_only_the_alternative_in_inventory(self):
        self._give("item_forest_berries", 2)
        can_do, message = self.manager.can_craft(self.player, self.recipe)
        self.assertTrue(can_do, message)

    def test_can_craft_fails_and_names_the_alternative_when_neither_is_available(self):
        can_do, message = self.manager.can_craft(self.player, self.recipe)
        self.assertFalse(can_do)
        self.assertIn("wild herbs", message)
        self.assertIn("forest berries", message)

    def test_select_recipe_ingredients_prefers_the_primary_when_both_are_available(self):
        self._give("item_wild_herbs", 2)
        self._give("item_forest_berries", 2)
        selected = self.manager.select_recipe_ingredients(self.player, self.recipe)
        self.assertTrue(all(item.obj_id == "item_wild_herbs" for item in selected))

    def test_select_recipe_ingredients_falls_through_to_the_alternative(self):
        self._give("item_forest_berries", 2)
        selected = self.manager.select_recipe_ingredients(self.player, self.recipe)
        self.assertTrue(all(item.obj_id == "item_forest_berries" for item in selected))

    def test_quality_score_is_unpenalized_when_the_primary_is_used(self):
        self._give("item_wild_herbs", 2, material_quality_score=3)
        selected = self.manager.select_recipe_ingredients(self.player, self.recipe)
        score = self.manager.ingredient_quality_score(self.player, self.recipe, selected)
        self.assertEqual(3, score)

    def test_quality_score_is_penalized_when_the_alternative_is_used(self):
        self._give("item_forest_berries", 2, material_quality_score=3)
        selected = self.manager.select_recipe_ingredients(self.player, self.recipe)
        score = self.manager.ingredient_quality_score(self.player, self.recipe, selected)
        self.assertEqual(2, score)

    def test_quality_score_penalty_never_drops_below_zero(self):
        self._give("item_forest_berries", 2, material_quality_score=0)
        selected = self.manager.select_recipe_ingredients(self.player, self.recipe)
        score = self.manager.ingredient_quality_score(self.player, self.recipe, selected)
        self.assertEqual(0, score)