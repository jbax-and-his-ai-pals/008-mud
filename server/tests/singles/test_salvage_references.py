# tests/singles/test_salvage_references.py
"""What an item breaks down into, authored as a reference.

Salvage output used to be an item id on the template or a rule keyed by the
engine class the item happened to be (`Weapon`, `Armor`). The class name was a
proxy for the family, and a proxy is what it behaved like: any new weapon
template joined the weapon rule without anyone deciding it should.

Both seams now speak one vocabulary. `engine/items/references.py` answers "does
this item count?" for a recipe ingredient, a vendor's buy order and a salvage
rule alike, and a rule may key on what a thing *is* rather than on the class it
resolves to.
"""
from typing import Any, Dict

from tests.fixtures import GameTestBase
from engine.contracts import ContractRegistry
from engine.items.item_factory import ItemFactory


CONTRACTS: Dict[str, Any] = {
    "schema_version": 1,
    "label": "Salvage fixtures",
    "item_families": [
        {"id": "salvaged_part", "label": "salvaged part", "item_class": "Junk",
         "capabilities": ["crafting_material"]},
        {"id": "gear", "label": "gear", "item_class": "Armor",
         "capabilities": ["equippable"]},
        {"id": "raw", "label": "raw material", "item_class": "Item",
         "capabilities": ["crafting_input"]},
    ],
}

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "item_scrap": {"type": "Item", "name": "scrap", "value": 4, "weight": 0.2},
    "item_worn_part": {
        "type": "Item", "name": "worn part", "value": 3, "weight": 0.1,
        "item_family": "salvaged_part",
    },
    "item_vest": {
        "type": "Armor", "name": "impact vest", "value": 90, "weight": 3.0,
        "item_family": "gear",
    },
    "item_custom_plate": {
        "type": "Item", "name": "custom plate", "value": 12, "weight": 0.5,
        "item_family": "raw",
        "properties": {"salvage_output": {"item_id": "item_scrap", "quantity_per_weight": 4.0}},
    },
}


class SalvageTestBase(GameTestBase):
    def setUp(self):
        super().setUp()
        self.registry = ContractRegistry()
        self.registry.ingest(CONTRACTS)
        self.assertEqual([], list(self.registry.issues))
        self.world.contract_registry = self.registry
        self.manager = self.game.crafting_manager

        self._added = []
        for item_id, template in TEMPLATES.items():
            if item_id not in self.world.item_templates:
                self._added.append(item_id)
            self.world.item_templates[item_id] = dict(template)
        self.addCleanup(self._remove_templates)

        self._ruleset = self.world.content_set.ruleset
        self._original_crafting = self._ruleset.get("crafting")
        self.addCleanup(self._restore_ruleset)

    def _remove_templates(self):
        for item_id in self._added:
            self.world.item_templates.pop(item_id, None)

    def _restore_ruleset(self):
        if self._original_crafting is None:
            self._ruleset.pop("crafting", None)
        else:
            self._ruleset["crafting"] = self._original_crafting

    def set_salvage_rules(self, rules: Dict[str, Any]):
        self._ruleset["crafting"] = {"salvage_rules": rules}

    def give(self, item_id: str, material_quality_score: int = 0):
        item = ItemFactory.create_item_from_template(item_id, self.world)
        self.assertIsNotNone(item, "template %r produced no item" % item_id)
        if material_quality_score:
            item.properties["material_quality_score"] = material_quality_score
        self.player.inventory.add_item(item)
        return item


class TestSalvageRuleLookup(SalvageTestBase):

    def test_a_family_rule_applies_to_a_member_of_the_family(self):
        self.set_salvage_rules({
            "by_family": {"salvaged_part": {"item_id": "item_scrap", "quantity_per_weight": 5.0}},
        })
        rule = self.manager.salvage_output_for(self.give("item_worn_part"))
        self.assertIsNotNone(rule)
        self.assertEqual("family", rule["source"])
        self.assertEqual("item_scrap", rule["reference"]["item_id"])

    def test_a_family_rule_reaches_a_member_the_rule_never_named(self):
        """Which is the whole point of keying on the family, not the class."""
        self.set_salvage_rules({
            "by_family": {"gear": {"item_id": "item_scrap", "quantity_per_weight": 1.0}},
        })
        self.world.item_templates["item_new_vest"] = {
            "type": "Armor", "name": "new vest", "value": 50, "weight": 2.0, "item_family": "gear",
        }
        self.addCleanup(self.world.item_templates.pop, "item_new_vest", None)
        rule = self.manager.salvage_output_for(self.give("item_new_vest"))
        self.assertEqual("family", rule["source"])

    def test_the_items_own_output_beats_every_rule(self):
        self.set_salvage_rules({
            "by_family": {"raw": {"item_id": "item_scrap"}},
        })
        rule = self.manager.salvage_output_for(self.give("item_custom_plate"))
        self.assertEqual("item", rule["source"])
        self.assertEqual(4.0, rule["quantity_per_weight"])

    def test_a_class_rule_still_answers_for_a_template_with_no_family(self):
        """The older spelling, and the only key a family-less template has."""
        self.set_salvage_rules({
            "default_item_id": "item_scrap",
            "Armor": {"item_id": "item_scrap", "quantity_per_weight": 2.0},
        })
        # A template that predates families: nothing on it, and nothing on the
        # instance built from it.
        self.world.item_templates["item_familyless_vest"] = {
            "type": "Armor", "name": "familyless vest", "value": 50, "weight": 2.0,
        }
        self.addCleanup(self.world.item_templates.pop, "item_familyless_vest", None)
        bare = ItemFactory.create_item_from_template("item_familyless_vest", self.world)
        bare.properties.pop("item_family", None)
        rule = self.manager.salvage_output_for(bare)
        self.assertEqual("class", rule["source"])

    def test_an_instance_family_beats_the_template_it_came_from(self):
        """A rolled instance carries its own family; the template is the fallback."""
        self.set_salvage_rules({
            "by_family": {
                "gear": {"item_id": "item_worn_part"},
                "raw": {"item_id": "item_scrap"},
            },
        })
        item = self.give("item_vest")
        item.properties["item_family"] = "raw"
        rule = self.manager.salvage_output_for(item)
        self.assertEqual("item_scrap", rule["reference"]["item_id"])

    def test_a_family_rule_wins_over_the_class_rule_it_used_to_be_a_proxy_for(self):
        self.set_salvage_rules({
            "by_family": {"gear": {"item_id": "item_scrap", "quantity_per_weight": 1.0}},
            "Armor": {"item_id": "item_worn_part"},
        })
        rule = self.manager.salvage_output_for(self.give("item_vest"))
        self.assertEqual("family", rule["source"])
        self.assertIn("quantity_per_weight", rule["reference"])

    def test_no_rule_and_no_default_means_it_cannot_be_salvaged(self):
        self.set_salvage_rules({"by_family": {"raw": {"item_id": "item_scrap"}}})
        item = self.give("item_vest")
        self.assertIsNone(self.manager.salvage_output_for(item))
        self.assertIn("cannot salvage", self.manager.salvage(self.player, item))

    def test_a_rule_naming_nothing_is_not_a_rule(self):
        self.set_salvage_rules({"by_family": {"gear": {"quantity_per_weight": 2.0}}})
        self.assertIsNone(self.manager.salvage_output_for(self.give("item_vest")))


class TestSalvageOutcome(SalvageTestBase):

    def test_a_weight_scaled_rule_yields_by_weight(self):
        self.set_salvage_rules({
            "by_family": {"gear": {"item_id": "item_scrap", "quantity_per_weight": 2.0}},
        })
        self.give("item_vest")
        result = self.manager.salvage(self.player, self.player.inventory.slots[0].item)
        self.assertIn("you salvage", result.lower())
        self.assertEqual(6, self.player.inventory.count_item("item_scrap"))

    def test_a_rule_with_no_rate_yields_exactly_one(self):
        self.set_salvage_rules({"by_family": {"gear": {"item_id": "item_scrap"}}})
        self.give("item_vest")
        self.manager.salvage(self.player, self.player.inventory.slots[0].item)
        self.assertEqual(1, self.player.inventory.count_item("item_scrap"))

    def test_the_items_own_rate_is_used_when_it_has_one(self):
        self.set_salvage_rules({"by_family": {"raw": {"item_id": "item_worn_part"}}})
        self.give("item_custom_plate")
        self.manager.salvage(self.player, self.player.inventory.slots[0].item)
        self.assertEqual(2, self.player.inventory.count_item("item_scrap"))

    def test_a_reference_output_may_name_a_family(self):
        self.set_salvage_rules({
            "by_family": {"gear": {"item_family": "salvaged_part", "quantity_per_weight": 1.0}},
        })
        self.give("item_vest")
        self.manager.salvage(self.player, self.player.inventory.slots[0].item)
        self.assertEqual(3, self.player.inventory.count_item("item_worn_part"))

    def test_the_default_is_what_an_unruled_item_comes_back_as(self):
        self.set_salvage_rules({"by_family": {"raw": {"item_id": "item_worn_part"}}, "default_item_id": "item_scrap"})
        self.give("item_vest")
        self.manager.salvage(self.player, self.player.inventory.slots[0].item)
        self.assertEqual(1, self.player.inventory.count_item("item_scrap"))

    def test_the_spent_item_is_gone_and_nothing_is_duplicated(self):
        self.set_salvage_rules({"by_family": {"gear": {"item_id": "item_scrap"}}})
        self.give("item_vest")
        self.manager.salvage(self.player, self.player.inventory.slots[0].item)
        self.assertEqual(0, self.player.inventory.count_item("item_vest"))
