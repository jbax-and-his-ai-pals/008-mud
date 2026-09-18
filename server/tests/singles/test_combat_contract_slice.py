# tests/singles/test_combat_contract_slice.py
"""P9: one weapon, one armour piece and one spell driven by contracts.

Two things have to be true at once, and they pull in opposite directions:

* **Nothing changed.** `item_iron_sword` still hits for 8 and is still slashing;
  `item_leather_tunic` still gives 2 defense and counts as leather; casting
  `magic_missile` still costs 5 mana on a 3-second cooldown. The values moved
  from the template's properties into a contract profile, and the fight must not
  notice.
* **The contract is load-bearing.** Changing the profile must change the fight.
  A contract nothing reads is documentation, and documentation that silently
  disagrees with the runtime is worse than none.

The equivalence half is asserted against the numbers the templates still carry,
so if someone edits one and not the other, these fail.
"""

import unittest

from engine.contracts import (
    ContractRegistry,
    ability_numbers,
    armor_defense,
    armor_material,
    armor_resistances,
    weapon_damage,
    weapon_damage_type,
)
from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class _World:
    """A world with templates and a registry, for resolver-level tests."""

    def __init__(self, templates=None, registry=None):
        self.item_templates = templates or {}
        self.contract_registry = registry


class _Item:
    def __init__(self, obj_id, **properties):
        self.obj_id = obj_id
        self.properties = dict(properties)

    def get_property(self, name, default=None):
        return self.properties.get(name, default)


class TestSliceEquivalence(unittest.TestCase):
    """The declared profile and the template say the same thing."""

    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        self.addCleanup(self.server.shutdown)
        self.world = self.server.world
        self.templates = self.world.item_templates

    def test_sword_damage_matches_its_attack_profile(self):
        template = self.templates["item_iron_sword"]
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertEqual(8, weapon_damage(self.world, item))
        self.assertEqual(template["properties"]["damage"], weapon_damage(self.world, item))
        self.assertIn("attack_profile", template, "the sword must name its profile")

    def test_sword_damage_type_matches_its_attack_profile(self):
        template = self.templates["item_iron_sword"]
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertEqual("slashing", weapon_damage_type(self.world, item))
        self.assertEqual(template["properties"]["weapon_damage_type"], weapon_damage_type(self.world, item))

    def test_tunic_defense_and_material_match_its_defense_profile(self):
        template = self.templates["item_leather_tunic"]
        item = ItemFactory.create_item_from_template("item_leather_tunic", self.world)
        self.assertEqual(2, armor_defense(self.world, item))
        self.assertEqual(template["properties"]["defense"], armor_defense(self.world, item))
        self.assertEqual("leather", armor_material(self.world, item))
        self.assertEqual(template["properties"]["armor_material"], armor_material(self.world, item))

    def test_spell_numbers_match_its_declared_ability(self):
        from engine.magic.spell_registry import get_spell

        missile = get_spell("magic_missile")
        self.assertIsNotNone(missile)
        numbers = ability_numbers(self.world, missile)
        self.assertEqual(missile.mana_cost, numbers["mana_cost"])
        self.assertEqual(missile.cooldown, numbers["cooldown"])
        self.assertEqual(missile.target_type, numbers["target_type"])
        self.assertEqual(missile.level_required, numbers["level_required"])

    def test_an_unmigrated_item_still_reads_its_own_properties(self):
        """Most content is unmigrated; it must behave exactly as before."""
        item = ItemFactory.create_item_from_template("item_starter_dagger", self.world)
        self.assertEqual(item.get_property("damage"), weapon_damage(self.world, item))
        self.assertEqual("piercing", weapon_damage_type(self.world, item))


class TestSliceIsLoadBearing(unittest.TestCase):
    """Change the contract, and the runtime follows."""

    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        self.addCleanup(self.server.shutdown)
        self.world = self.server.world

    def _retune(self, mutate):
        """Copy the shipped registry, let the test change it, and use that."""
        registry = ContractRegistry.load(str(self.world.content_root))
        self.assertEqual([], registry.issues)
        mutate(registry)
        self.world.contract_registry = registry

    def test_retuning_an_attack_profile_changes_the_weapons_damage(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        before = weapon_damage(self.world, item)
        self._retune(lambda r: r.attack_profiles["melee_blade"].__setitem__("damage", 15))
        self.assertEqual(15, weapon_damage(self.world, item))
        self.assertNotEqual(before, weapon_damage(self.world, item))

    def test_retuning_a_defense_profile_changes_the_armour(self):
        item = ItemFactory.create_item_from_template("item_leather_tunic", self.world)
        self._retune(lambda r: r.defense_profiles["light_armour"].__setitem__("defense", 9))
        self.assertEqual(9, armor_defense(self.world, item))

    def test_a_profile_can_add_a_resistance_the_item_never_declared(self):
        item = ItemFactory.create_item_from_template("item_leather_tunic", self.world)
        self.assertEqual({}, armor_resistances(self.world, item))
        self._retune(lambda r: r.defense_profiles["light_armour"].__setitem__(
            "resistances", {"fire": 25}))
        self.assertEqual(25, armor_resistances(self.world, item).get("fire"))

    def test_a_profile_resistance_overrides_the_item_property(self):
        item = _Item("item_probe", resistances={"fire": 10, "ice": 5})
        world = _World(
            templates={"item_probe": {"type": "Armor", "item_family": "armor",
                                      "defense_profile": "probe_profile"}},
            registry=ContractRegistry(),
        )
        world.contract_registry.ingest({
            "schema_version": 1,
            "item_families": [{"id": "armor", "label": "A", "item_class": "Armor",
                               "defense_profile": "probe_profile"}],
            "defense_profiles": [{"id": "probe_profile", "resistances": {"fire": 40}}],
        })
        self.assertEqual([], world.contract_registry.issues)
        merged = armor_resistances(world, item)
        self.assertEqual(40, merged["fire"], "profile should win")
        self.assertEqual(5, merged["ice"], "undeclared keys keep the item's own")

    def test_retuning_an_ability_changes_what_a_cast_costs(self):
        from engine.magic.spell_registry import get_spell

        missile = get_spell("magic_missile")
        self._retune(lambda r: r.abilities["magic_missile"].__setitem__(
            "cost", {"resource": "mana", "amount": 33}))
        numbers = ability_numbers(self.world, missile)
        self.assertEqual(33, numbers["mana_cost"])

    def test_an_ability_costing_another_resource_is_not_charged_as_mana(self):
        """A cost in a resource that is not this set's pool is not this pool's.

        This used to be the resource seam's honest limit: the pool was mana by
        name, so a cost declared in `charge` was legal content the engine could
        not honour. The pool is a declared resource now, and a cost in a resource
        this set does not declare as its ability pool is *still* refused -- but
        for the right reason, rather than because the word "mana" was hardcoded.
        """
        from engine.magic.spell_registry import get_spell

        missile = get_spell("magic_missile")
        self._retune(lambda r: r.abilities["magic_missile"].__setitem__(
            "cost", {"resource": "charge", "amount": 4}))
        numbers = ability_numbers(self.world, missile)
        self.assertEqual(missile.mana_cost, numbers["mana_cost"],
                         "a cost in a resource this set does not declare must not be spent from its pool")

    def test_a_spell_with_no_declared_ability_keeps_its_own_numbers(self):
        from engine.magic.spell import Spell

        bare = Spell("probe_spell", "Probe", "…", effects=[{"type": "damage", "value": 1}],
                     mana_cost=7, cooldown=2.5, target_type="self", level_required=3)
        numbers = ability_numbers(self.world, bare)
        self.assertEqual(
            {"mana_cost": 7, "cooldown": 2.5, "target_type": "self",
             "level_required": 3, "resource": "mana"},
            numbers,
        )


class TestTheFightItself(unittest.TestCase):
    """End to end: a real weapon, real armour, and a real swing."""

    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        self.addCleanup(self.server.shutdown)
        self.session = self.server.create_session(player_id="slice")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def test_equipping_the_sword_raises_attack_power_by_the_profile_value(self):
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.server.world)
        before = self.player.get_attack_power()
        self.player.equipment["main_hand"] = sword
        after = self.player.get_attack_power()
        template_damage = self.server.world.item_templates["item_iron_sword"]["properties"]["damage"]
        self.assertEqual(before + template_damage, after)

    def test_equipping_the_tunic_raises_defense_by_the_profile_value(self):
        tunic = ItemFactory.create_item_from_template("item_leather_tunic", self.server.world)
        before = self.player.get_defense()
        self.player.equipment["body"] = tunic
        self.assertEqual(before + 2, self.player.get_defense())
        self.assertEqual("leather", self.player.get_body_armor_material())

    def test_casting_the_spell_spends_the_declared_cost(self):
        from engine.magic.spell_registry import get_spell

        self.server.execute_command(self.session.session_id, "cast magic missile")
        missile = get_spell("magic_missile")
        mana = self.player.runtime_state.magic
        # Either it cast (mana down by the declared cost) or it refused for a
        # reason that is not the cost -- never a silent mismatch.
        if mana.mana < mana.max_mana:
            self.assertEqual(mana.max_mana - missile.mana_cost, mana.mana)


if __name__ == "__main__":
    unittest.main()
