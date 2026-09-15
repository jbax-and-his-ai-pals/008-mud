"""The field-alchemy items must exercise real effect, cleanse, and target paths."""

from engine.game_object import GameObject
from engine.items.item_factory import ItemFactory
from tests.fixtures import GameTestBase


class TestCraftedConsumables(GameTestBase):
    def _item(self, item_id: str):
        item = ItemFactory.create_item_from_template(item_id, self.world)
        self.assertIsNotNone(item, item_id)
        return item

    def test_marshguard_is_a_temporary_poison_resistance(self):
        tonic = self._item("item_marshguard_tonic")
        starting_resistance = self.player.get_resistance("poison")

        result = tonic.use(self.player)

        self.assertIn("Marshguard takes hold", result)
        self.assertEqual(0, tonic.get_property("uses"))
        self.assertEqual(starting_resistance + 60, self.player.get_resistance("poison"))
        self.assertTrue(self.player.has_effect("Marshguard"))

        messages = self.player.process_active_effects(self.world.clock.now() + 181.0, 181.0)
        self.assertEqual(starting_resistance, self.player.get_resistance("poison"))
        self.assertFalse(self.player.has_effect("Marshguard"))
        self.assertTrue(any("Marshguard" in message and "wears off" in message for message in messages))

    def test_trailblazer_uses_the_same_temporary_effect_contract(self):
        tonic = self._item("item_trailblazer_tonic")
        starting_agility = self.player.get_effective_stat("agility")

        result = tonic.use(self.player)

        self.assertIn("Trailblazer takes hold", result)
        self.assertEqual(starting_agility + 4, self.player.get_effective_stat("agility"))
        self.assertEqual(180.0, self.player.active_effects[-1]["duration_remaining"])

    def test_purifying_draught_cleanses_tagged_afflictions(self):
        draught = self._item("item_purifying_draught")
        self.player.apply_effect({
            "name": "Test Venom",
            "type": "dot",
            "base_duration": 30.0,
            "damage_per_tick": 1,
            "tick_interval": 3.0,
            "damage_type": "poison",
            "tags": ["poison"],
        }, self.world.clock.now())

        result = draught.use(self.player)

        self.assertIn("cleanse", result)
        self.assertFalse(self.player.has_effect("Test Venom"))
        self.assertEqual(0, draught.get_property("uses"))

    def test_sunfire_flask_requires_a_target_and_deals_its_authored_damage(self):
        flask = self._item("item_sunfire_flask")
        self.assertIn("on whom", flask.use(self.player))
        self.assertEqual(1, flask.get_property("uses"))

        target = GameObject(name="Practice Target")
        target.health = 50
        result = flask.use(self.player, target=target)

        self.assertIn("hurl", result)
        self.assertEqual(32, target.health)
        self.assertEqual(0, flask.get_property("uses"))

    def test_all_field_alchemy_results_have_beginner_station_recipes(self):
        recipes = self.game.crafting_manager.recipes
        expected_results = {
            "brew_marshguard_tonic": "item_marshguard_tonic",
            "brew_trailblazer_tonic": "item_trailblazer_tonic",
            "brew_purifying_draught": "item_purifying_draught",
            "distill_sunfire_flask": "item_sunfire_flask",
        }

        for recipe_id, result_item_id in expected_results.items():
            recipe = recipes[recipe_id]
            self.assertEqual(result_item_id, recipe.result_item_id)
            self.assertEqual("alchemy_table", recipe.station_required)
            self.assertEqual(0, recipe.difficulty)
