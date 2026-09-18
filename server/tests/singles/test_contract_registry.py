# tests/singles/test_contract_registry.py
"""P9 contracts: the schema, the registry, and the one consumer wired so far.

The problem these exist for: the engine branched on genre words. `ItemFactory`
mapped `"Gem"` to a class, the instance generator checked `type == "Gem"`, and a
sci-fi content set inherited mana and spells because they were engine nouns
rather than content declarations. The registry replaces the branch with a
declaration, and refuses — loudly — anything it cannot describe.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.contracts import (
    CONTRACT_SCHEMAS,
    DEFAULT_GENERATION_PROFILE,
    SCHEMA_VERSION,
    ContractRegistry,
    generation_profile_for_template,
    item_class_for_template,
    validate_fields,
)
from engine.items.gem_generator import GemGenerator
from engine.items.instance_generator import InstanceGenerator
from engine.server.content_set import validate_content_set
from tests.fixtures import FANTASY_FRONTIER

CONTENT_ROOT = Path(FANTASY_FRONTIER) / "data"


class _World:
    """Minimal world: item templates and whatever registry a test hands it."""

    def __init__(self, templates=None, registry=None):
        self.item_templates = templates or {}
        self.contract_registry = registry


def _payload(**overrides):
    base = {
        "schema_version": SCHEMA_VERSION,
        "resources": [{"id": "charge", "label": "Charge", "kind": "ability"}],
        "item_families": [{
            "id": "cell", "label": "Cell", "item_class": "Consumable",
            "capabilities": ["usable"], "resource": "charge",
        }],
        "generation_profiles": [],
        "attack_profiles": [],
        "defense_profiles": [],
        "abilities": [],
        "effect_packets": [],
    }
    base.update(overrides)
    return base


# -- the schema language ------------------------------------------------------

class TestSchemaLanguage(unittest.TestCase):
    def test_unknown_field_is_an_error(self):
        """A typo must not sit in content looking live while nothing reads it."""
        issues = []
        validate_fields({"id": "x", "generation_profil": "y"}, CONTRACT_SCHEMAS["item_families"], "f", issues)
        self.assertTrue(any("generation_profil" in issue and "not a field" in issue for issue in issues), issues)

    def test_missing_required_field_is_an_error(self):
        issues = []
        validate_fields({"label": "x"}, CONTRACT_SCHEMAS["item_families"], "f", issues)
        self.assertTrue(any("f.id is required" in issue for issue in issues), issues)

    def test_empty_required_field_is_an_error(self):
        issues = []
        validate_fields({"id": "  "}, CONTRACT_SCHEMAS["item_families"], "f", issues)
        self.assertTrue(any("may not be empty" in issue for issue in issues), issues)

    def test_wrong_scalar_types_are_reported_with_the_path(self):
        issues = []
        validate_fields(
            {"id": "x", "item_class": "Item", "debug_only": "yes"},
            CONTRACT_SCHEMAS["item_families"], "families[2]", issues,
        )
        self.assertTrue(any("families[2].debug_only must be true or false" in i for i in issues), issues)

    def test_enum_rejects_an_unknown_value(self):
        issues = []
        validate_fields({"id": "x", "label": "X", "kind": "vibes"}, CONTRACT_SCHEMAS["resources"], "r", issues)
        self.assertTrue(any("must be one of" in issue for issue in issues), issues)

    def test_nested_tiers_are_validated_in_place(self):
        issues = []
        validate_fields(
            {"id": "p", "item_family": "cell", "size_tiers": [{"id": "big", "score": "three"}]},
            CONTRACT_SCHEMAS["generation_profiles"], "profiles[0]", issues,
        )
        self.assertTrue(any("size_tiers[0].score must be a whole number" in i for i in issues), issues)

    def test_numeric_bounds_are_enforced(self):
        issues = []
        validate_fields(
            {"id": "p", "item_family": "cell", "size_bias": 1},
            CONTRACT_SCHEMAS["generation_profiles"], "p", issues,
        )
        self.assertEqual([], issues)
        issues = []
        validate_fields({"id": "w", "label": "W", "damage_type": "x", "damage": -3},
                        CONTRACT_SCHEMAS["attack_profiles"], "a", issues)
        self.assertTrue(any("at least 0" in issue for issue in issues), issues)

    def test_map_values_are_type_checked(self):
        issues = []
        validate_fields({"id": "d", "resistances": {"fire": "lots"}},
                        CONTRACT_SCHEMAS["defense_profiles"], "d", issues)
        self.assertTrue(any("resistances.fire must be a number" in i for i in issues), issues)

    def test_duplicate_ids_are_refused(self):
        from engine.contracts import validate_list

        issues = []
        validate_list([{"id": "a", "label": "A", "kind": "vital"},
                       {"id": "a", "label": "Again", "kind": "vital"}],
                      CONTRACT_SCHEMAS["resources"], "resources", issues)
        self.assertTrue(any("already defined" in issue for issue in issues), issues)


# -- the registry -------------------------------------------------------------

class TestRegistryLoading(unittest.TestCase):
    def test_shipped_content_declares_contracts_that_load_cleanly(self):
        registry = ContractRegistry.load(str(CONTENT_ROOT))
        self.assertFalse(registry.is_empty, "fantasy_frontier declares no contracts")
        self.assertEqual([], registry.issues)
        self.assertEqual(SCHEMA_VERSION, registry.declared_version)

    def test_unknown_schema_version_is_refused_rather_than_guessed(self):
        registry = ContractRegistry()
        registry.ingest(_payload(schema_version=SCHEMA_VERSION + 1))
        self.assertTrue(any("refusing to read it" in issue for issue in registry.issues), registry.issues)
        self.assertTrue(registry.is_empty, "a refused file must not half-load")

    def test_missing_schema_version_is_refused(self):
        registry = ContractRegistry()
        payload = _payload()
        payload.pop("schema_version")
        registry.ingest(payload)
        self.assertTrue(any("schema_version" in issue for issue in registry.issues), registry.issues)

    def test_unknown_top_level_field_is_refused(self):
        registry = ContractRegistry()
        registry.ingest(_payload(spells=[{"id": "x"}]))
        self.assertTrue(any("spells" in issue and "not a field" in issue for issue in registry.issues))

    def test_a_profile_pointing_at_no_family_is_an_error(self):
        registry = ContractRegistry()
        registry.ingest(_payload(generation_profiles=[{"id": "p", "item_family": "ghost"}]))
        self.assertTrue(any("missing item family 'ghost'" in i for i in registry.issues), registry.issues)

    def test_an_ability_pointing_at_no_packet_is_an_error(self):
        registry = ContractRegistry()
        registry.ingest(_payload(abilities=[{"id": "zap", "effect_packet": "nope"}]))
        self.assertTrue(any("missing effect packet 'nope'" in i for i in registry.issues), registry.issues)

    def test_a_cost_naming_an_undeclared_resource_is_an_error(self):
        registry = ContractRegistry()
        registry.ingest(_payload(
            effect_packets=[{"id": "p", "kind": "damage"}],
            abilities=[{"id": "zap", "effect_packet": "p", "cost": {"resource": "plasma", "amount": 2}}],
        ))
        self.assertTrue(any("missing resource 'plasma'" in i for i in registry.issues), registry.issues)

    def test_a_family_naming_an_undeclared_resource_is_an_error(self):
        registry = ContractRegistry()
        registry.ingest(_payload(item_families=[{
            "id": "cell", "item_class": "Consumable", "resource": "plasma",
        }]))
        self.assertTrue(any("missing resource 'plasma'" in i for i in registry.issues), registry.issues)

    def test_structurally_broken_entries_are_not_half_registered(self):
        registry = ContractRegistry()
        registry.ingest(_payload(resources=[{"id": "charge", "label": "Charge", "kind": "not_a_kind"}]))
        self.assertEqual({}, registry.resources)
        self.assertTrue(registry.issues)

    def test_a_content_set_without_contracts_is_legal(self):
        with tempfile.TemporaryDirectory() as root:
            registry = ContractRegistry.load(root)
            self.assertTrue(registry.is_empty)
            self.assertEqual([], registry.issues)

    def test_lookups_resolve_families_profiles_and_tiers(self):
        registry = ContractRegistry.load(str(CONTENT_ROOT))
        self.assertEqual("Gem", registry.item_class_for_family("collectible_stone"))
        self.assertTrue(registry.family_has_capability("collectible_stone", "generated_instance"))
        self.assertFalse(registry.family_has_capability("collectible_stone", "equippable"))
        self.assertEqual("faceted_stone", registry.generation_profile("faceted_stone")["id"])
        self.assertEqual(["tiny", "small", "standard", "large", "magnificent"],
                         [t["id"] for t in registry.tiers("faceted_stone", "size_tiers")])

    def test_tiers_fall_back_to_the_neutral_default(self):
        registry = ContractRegistry.load(str(CONTENT_ROOT))
        self.assertEqual([t["id"] for t in DEFAULT_GENERATION_PROFILE["size_tiers"]],
                         [t["id"] for t in registry.tiers("no_such_profile", "size_tiers")])


# -- resolution, shared by both consumers -------------------------------------

class TestTemplateResolution(unittest.TestCase):
    def setUp(self):
        self.registry = ContractRegistry.load(str(CONTENT_ROOT))

    def test_family_wins_over_the_legacy_type(self):
        world = _World(registry=self.registry)
        # A template that still says Gem but declares a family resolves by family.
        template = {"type": "Item", "item_family": "collectible_stone"}
        self.assertEqual("Gem", item_class_for_template(world, template))

    def test_legacy_type_still_resolves_without_a_family(self):
        world = _World(registry=self.registry)
        self.assertEqual("Gem", item_class_for_template(world, {"type": "Gem"}))

    def test_type_resolves_with_no_registry_at_all(self):
        self.assertEqual("Gem", item_class_for_template(None, {"type": "Gem"}))
        self.assertEqual("", item_class_for_template(None, {"properties": {}}))

    def test_profile_comes_from_the_template_or_its_family(self):
        world = _World(registry=self.registry)
        self.assertEqual("faceted_stone",
                         generation_profile_for_template(world, {"item_family": "collectible_stone"}))
        self.assertEqual("other_profile",
                         generation_profile_for_template(
                             world, {"item_family": "collectible_stone", "generation_profile": "other_profile"}))

    def test_an_unknown_family_does_not_silently_resolve(self):
        world = _World(registry=self.registry)
        self.assertEqual("", item_class_for_template(world, {"item_family": "no_such_family"}))


# -- the wired consumer -------------------------------------------------------

class TestInstanceGeneratorUsesTheContract(unittest.TestCase):
    """The roll tables are content now, not engine constants."""

    def _world_with(self, size_tiers, prefix=""):
        profile = {
            "id": "stones", "item_family": "stone_family", "size_tiers": size_tiers,
        }
        if prefix:
            profile["property_prefix"] = prefix
        registry = ContractRegistry()
        registry.ingest(_payload(
            item_families=[{
                "id": "stone_family", "label": "Stones", "item_class": "Gem",
                "capabilities": ["generated_instance"], "generation_profile": "stones",
            }],
            generation_profiles=[profile],
        ))
        self.assertEqual([], registry.issues, registry.issues)
        return _World(
            templates={"item_probe": {
                "type": "Gem", "name": "probe", "value": 10, "weight": 0.1,
                "item_family": "stone_family", "generation_profile": "stones",
            }},
            registry=registry,
        )

    def test_authored_tiers_replace_the_built_in_ones(self):
        world = self._world_with([
            {"id": "pebble", "label": "pebble", "score": 1, "value_multiplier": 0.5, "weight_multiplier": 0.5},
            {"id": "boulder", "label": "boulder", "score": 5, "value_multiplier": 4.0, "weight_multiplier": 4.0},
        ])
        seen = set()
        for _ in range(40):
            gem = GemGenerator.generate_gem(world, level=1, template_id="item_probe")
            self.assertIsNotNone(gem)
            seen.add(gem.get_property("instance_size"))
        self.assertTrue(seen <= {"pebble", "boulder"}, seen)
        self.assertTrue(seen, "no instance rolled")

    def test_a_declared_property_prefix_is_what_writes_the_legacy_keys(self):
        """`gem_size` exists because the profile says so, not because we say gem."""
        neutral = self._world_with([
            {"id": "pebble", "label": "pebble", "score": 1, "value_multiplier": 0.5, "weight_multiplier": 0.5},
        ])
        without = GemGenerator.generate_gem(neutral, level=1, template_id="item_probe")
        self.assertIsNotNone(without)
        self.assertEqual("pebble", without.get_property("instance_size"))
        self.assertIsNone(without.get_property("gem_size"))

        prefixed = self._world_with([
            {"id": "pebble", "label": "pebble", "score": 1, "value_multiplier": 0.5, "weight_multiplier": 0.5},
        ], prefix="gem")
        with_prefix = GemGenerator.generate_gem(prefixed, level=1, template_id="item_probe")
        self.assertIsNotNone(with_prefix)
        self.assertEqual("pebble", with_prefix.get_property("gem_size"))
        self.assertEqual("item_probe", with_prefix.get_property("gem_type_id"))

    def test_the_default_tables_still_apply_without_declared_bands(self):
        world = self._world_with([])
        gem = GemGenerator.generate_gem(world, level=1, template_id="item_probe")
        self.assertIsNotNone(gem)
        self.assertIn(gem.get_property("instance_size"), [t["id"] for t in DEFAULT_GENERATION_PROFILE["size_tiers"]])

    def test_the_class_name_alone_no_longer_makes_a_template_roll(self):
        """The pre-P9 `type == "Gem"` fallback is retired, not kept as a branch.

        Content says a template rolls instances by naming a family that declares
        `generated_instance` and rides a profile. A bare `type: Gem` with no
        family now rolls nothing -- and the content validator names the template
        that forgot, so the mistake is louder than the silent fallback was.
        """
        bare = _World(templates={"item_probe": {"type": "Gem", "name": "probe", "value": 10}})
        self.assertFalse(InstanceGenerator.is_generated_template(bare, "item_probe"))
        self.assertIsNone(GemGenerator.generate_gem(bare, level=1, template_id="item_probe"))

    def test_a_family_makes_a_template_a_stone(self):
        """`is_gem_template` follows the contract, not the word Gem."""
        world = _World(templates={"item_cell": {"type": "Item", "item_family": "cell"}})
        self.assertFalse(GemGenerator.is_gem_template(world, "item_cell"))
        stone_world = _World(
            templates={"item_stone": {"type": "Item", "item_family": "collectible_stone"}},
            registry=ContractRegistry.load(str(CONTENT_ROOT)),
        )
        self.assertTrue(GemGenerator.is_gem_template(stone_world, "item_stone"))


# -- the validation gate ------------------------------------------------------

class TestContractValidation(unittest.TestCase):
    """A broken contract fails content validation, not a play session."""

    def _content_set_with(self, mutate) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        target = root / "content_set"
        shutil.copytree(Path(FANTASY_FRONTIER), target)
        path = target / "data" / "contracts" / "world_contracts.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target

    def _errors(self, target: Path) -> list[str]:
        return [i.message for i in validate_content_set(target) if i.severity == "error"]

    def test_shipped_contracts_validate(self):
        self.assertEqual([], self._errors(Path(FANTASY_FRONTIER)))

    def test_an_unknown_schema_version_fails_validation(self):
        target = self._content_set_with(lambda p: p.__setitem__("schema_version", 99))
        self.assertTrue(any("schema_version" in message for message in self._errors(target)))

    def test_an_unknown_family_field_fails_validation(self):
        def mutate(payload):
            payload["item_families"][0]["item_famly"] = "typo"
        target = self._content_set_with(mutate)
        messages = self._errors(target)
        self.assertTrue(any("item_famly" in message for message in messages), messages)

    def test_a_family_naming_an_unknown_engine_class_fails_validation(self):
        def mutate(payload):
            payload["item_families"][0]["item_class"] = "NotAClass"
        target = self._content_set_with(mutate)
        self.assertTrue(any("not an item class" in message for message in self._errors(target)))

    def test_a_dangling_profile_reference_fails_validation(self):
        def mutate(payload):
            payload["generation_profiles"][0]["item_family"] = "ghost_family"
        target = self._content_set_with(mutate)
        self.assertTrue(any("missing item family 'ghost_family'" in m for m in self._errors(target)))

    def test_a_template_naming_an_undefined_family_fails_validation(self):
        """Every shipped template names a family now, so clearing them is refused.

        Before the family sweep this test asserted the opposite -- that removing
        the family list upset nothing -- because no template used one. Now the
        whole content set references families, which is exactly what makes the
        reference gate worth having.
        """
        def mutate(payload):
            payload["item_families"] = []
            payload["generation_profiles"] = []
        target = self._content_set_with(mutate)
        messages = self._errors(target)
        self.assertTrue(
            any("declares item_family" in message for message in messages),
            "clearing families while templates reference them must be an error",
        )


if __name__ == "__main__":
    unittest.main()
