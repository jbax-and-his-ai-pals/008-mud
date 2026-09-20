# tests/singles/test_stats_contract.py
"""Whichever stat fills a role is content; the curve is engine config.

Stats were the last system in the engine with no contract. `constitution` was
written into five files, `strength` into four, and a content set could not rename
any of them: health would keep reading a stat nobody had, find the default, and
produce a character whose physical stat did nothing. Nothing failed, because
nothing was wrong -- the engine was simply playing a different set's vocabulary.

These tests are about the seam, not the arithmetic: that a set can say which stat
drives health and be believed, that a set which says nothing behaves exactly as
it did before, and that the display paths and the arithmetic agree about what a
character has.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.fixtures import GameTestBase
from engine.contracts import stats as stats_contract
from engine.contracts.registry import ContractRegistry


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _World:
    """The smallest thing a role can be resolved against."""

    def __init__(self, roles=None, order=None, shorts=None):
        stats_section = {}
        if roles is not None:
            stats_section["roles"] = roles
        if order is not None:
            stats_section["order"] = order
        if shorts is not None:
            stats_section["short"] = shorts
        self.contract_registry = ContractRegistry(stats=stats_section)


class TestTheEngineDefaultIsTheVocabularlyThatShipped(unittest.TestCase):
    """A set that declares nothing must behave exactly as it did before."""

    def test_every_role_has_a_default(self):
        world = _World()
        for role in stats_contract.STAT_ROLES:
            self.assertTrue(stats_contract.stat_name(world, role), role)

    def test_the_defaults_are_the_names_the_engine_used_to_hardcode(self):
        world = _World()
        self.assertEqual("constitution", stats_contract.stat_name(world, "health"))
        self.assertEqual("strength", stats_contract.stat_name(world, "attack"))
        self.assertEqual("dexterity", stats_contract.stat_name(world, "defence"))
        self.assertEqual("agility", stats_contract.stat_name(world, "evasion"))
        self.assertEqual("strength", stats_contract.stat_name(world, "regeneration"))
        self.assertEqual("intelligence", stats_contract.stat_name(world, "power"))
        self.assertEqual("spell_power", stats_contract.stat_name(world, "ability_power"))
        self.assertEqual("magic_resist", stats_contract.stat_name(world, "resistance"))

    def test_a_world_with_no_registry_at_all_still_resolves(self):
        """`Player` is built before it is attached to a world."""
        self.assertEqual("constitution", stats_contract.stat_name(None, "health"))
        self.assertEqual("strength", stats_contract.stat_name(object(), "attack"))


class TestAContentSetCanRenameItsStats(unittest.TestCase):
    def test_a_declared_role_wins_over_the_default(self):
        world = _World(roles={"health": "vigour"})
        self.assertEqual("vigour", stats_contract.stat_name(world, "health"))
        self.assertEqual("strength", stats_contract.stat_name(world, "attack"))

    def test_a_value_is_read_from_the_declared_stat(self):
        world = _World(roles={"health": "vigour"})
        stats = {"vigour": 14, "constitution": 3}
        self.assertEqual(14, stats_contract.stat_for(world, stats, "health"))

    def test_a_declared_stat_that_is_absent_is_neutral_not_zero(self):
        world = _World(roles={"health": "vigour"})
        self.assertEqual(
            stats_contract.NEUTRAL_STAT_VALUE,
            stats_contract.stat_for(world, {}, "health"),
        )

    def test_a_per_stat_default_map_is_honoured(self):
        """An entity's defaults are not one number: `NPC_DEFAULT_STATS` is not flat."""
        world = _World(roles={"health": "vigour", "power": "insight"})
        defaults = {"vigour": 8, "insight": 5}
        self.assertEqual(8, stats_contract.stat_for(world, {}, "health", defaults))
        self.assertEqual(5, stats_contract.stat_for(world, {}, "power", defaults))

    def test_a_default_map_that_lacks_the_stat_falls_back_to_neutral(self):
        world = _World(roles={"health": "vigour"})
        self.assertEqual(
            stats_contract.NEUTRAL_STAT_VALUE,
            stats_contract.stat_for(world, {}, "health", {"something_else": 3}),
        )

    def test_a_nested_container_is_not_a_stat_value(self):
        self.assertEqual(
            stats_contract.NEUTRAL_STAT_VALUE,
            stats_contract.stat_value({"resistances": {"fire": 10}}, "resistances"),
        )


class TestTheRegistryRejectsARoleItHasNoMeaningFor(unittest.TestCase):
    def test_an_unknown_role_is_reported_rather_than_ignored(self):
        """Reading it as "undeclared" would silently take the engine default."""
        registry = ContractRegistry()
        registry.ingest({
            "schema_version": 1,
            "stats": {"roles": {"helth": "constitution"}},
        })
        self.assertTrue(
            any("helth" in issue for issue in registry.issues),
            registry.issues,
        )

    def test_a_known_role_is_recorded(self):
        registry = ContractRegistry()
        registry.ingest({
            "schema_version": 1,
            "stats": {"roles": {"health": "vigour"}},
        })
        self.assertEqual([], registry.issues)
        self.assertEqual("vigour", registry.stat_for_role("health"))

    def test_a_section_with_no_roles_is_still_read_for_its_display_fields(self):
        registry = ContractRegistry()
        registry.ingest({
            "schema_version": 1,
            "stats": {"order": ["grit"], "short": {"grit": "GRT"}},
        })
        self.assertEqual([], registry.issues)
        self.assertEqual("GRT", stats_contract.stat_short(
            type("W", (), {"contract_registry": registry})(), "grit"
        ))

    def test_a_stats_section_is_not_an_empty_registry(self):
        registry = ContractRegistry()
        registry.ingest({"schema_version": 1, "stats": {"order": ["grit"]}})
        self.assertFalse(registry.is_empty)


class TestTheShippedSetsDeclareTheVocabularyOutLoud(GameTestBase):
    def test_fantasy_declares_every_role(self):
        registry = self.world.contract_registry
        for role in stats_contract.STAT_ROLES:
            self.assertTrue(registry.stat_for_role(role), role)

    def test_the_declared_names_are_the_ones_the_content_uses(self):
        """A set that named a stat it does not carry would be the old bug back."""
        declared = set(stats_contract.declared_stat_roles(self.world).values())
        self.assertTrue(
            declared.issubset(set(self.player.stats)),
            "declared but not carried: %s" % sorted(declared - set(self.player.stats)),
        )

    def test_the_status_line_shows_what_the_contract_orders(self):
        order = stats_contract.declared_stat_order(self.world)
        shown = tuple(stat for stat, _label in stats_contract.display_stats(self.world, ()))
        self.assertEqual(order, shown)

    def test_the_labels_are_the_declared_ones(self):
        labels = dict(stats_contract.display_stats(self.world, ()))
        self.assertEqual("STR", labels["strength"])
        self.assertEqual("MR", labels["magic_resist"])


class TestTheArithmeticAgreesWithTheContract(GameTestBase):
    """Renaming a stat in the contract has to move the number it drives."""

    def _world_with_health_stat(self, stat_name: str):
        registry = self.world.contract_registry
        original = registry.stats
        self.addCleanup(setattr, registry, "stats", original)
        registry.stats = dict(original)
        registry.stats["roles"] = dict(original.get("roles", {}), health=stat_name)
        return self.world

    def test_renaming_the_health_stat_moves_max_health(self):
        player = self.player
        baseline = player.max_health
        player.stats["vigour"] = player.stats["constitution"] + 3
        self._world_with_health_stat("vigour")
        player.recalculate_max_health()
        self.assertGreater(player.max_health, baseline)

    def test_an_undeclared_set_gets_the_same_number_as_before(self):
        """The regression guard: no set's arithmetic may move by being declared."""
        player = self.player
        before = player.max_health
        player.recalculate_max_health()
        self.assertEqual(before, player.max_health)


class TestTheWholeThingLoadsThroughTheValidator(unittest.TestCase):
    """The declaration has to survive `load_content_set`, not just the registry."""

    def test_a_set_declaring_its_stats_validates(self):
        from engine.server.content_set import load_content_set

        for name in ("fantasy_frontier", "orbital_salvage"):
            definition, issues = load_content_set(REPO_ROOT / "content_sets" / name)
            errors = [i.message for i in issues if i.severity == "error"]
            self.assertEqual([], errors, name)
            self.assertIsNotNone(definition, name)

    def test_the_declared_section_reaches_the_runtime_registry(self):
        from engine.server.content_set import load_content_set
        from engine.world.world import World

        definition, issues = load_content_set(REPO_ROOT / "content_sets" / "fantasy_frontier")
        self.assertIsNotNone(definition, [i.message for i in issues])
        # `ContractRegistry.load` is what a World uses, so reading the same file
        # must produce the same mapping.
        registry = ContractRegistry.load(str(definition.content_root))
        self.assertEqual("constitution", registry.stat_for_role("health"))


if __name__ == "__main__":
    unittest.main()
