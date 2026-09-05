# tests/singles/test_npc_factory_full.py
"""Coverage for engine/npcs/npc_factory.py: get_template_names/get_template's
no-world and no-npc_templates guards, create_npc_from_template's own no-
world guard, required_spells' duplicate-skip branch, random_spells' empty-
pool/zero-count skip, initial_inventory's non-dict/unknown-template/
invalid-item_id/non-list branches, and the outer exception handler."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory


class TestGetTemplateNames(GameTestBase):
    def test_no_world_returns_empty_list(self):
        self.assertEqual(NPCFactory.get_template_names(None), [])

    def test_world_without_npc_templates_attribute_returns_empty_list(self):
        class _BareWorld:
            pass
        self.assertEqual(NPCFactory.get_template_names(_BareWorld()), [])

    def test_returns_template_keys(self):
        names = NPCFactory.get_template_names(self.world)
        self.assertIn("goblin", names)


class TestGetTemplate(GameTestBase):
    def test_no_world_returns_none(self):
        self.assertIsNone(NPCFactory.get_template("goblin", None))

    def test_unknown_template_returns_none(self):
        self.assertIsNone(NPCFactory.get_template("totally_bogus_npc_xyz", self.world))

    def test_known_template_returns_a_copy(self):
        template = NPCFactory.get_template("goblin", self.world)
        self.assertIsNotNone(template)
        template["name"] = "Mutated"
        self.assertNotEqual(self.world.npc_templates["goblin"]["name"], "Mutated")


class TestCreateNpcFromTemplateGuards(GameTestBase):
    def test_no_world_returns_none(self):
        self.assertIsNone(NPCFactory.create_npc_from_template("goblin", None))

    def test_world_without_npc_templates_attribute_returns_none(self):
        class _BareWorld:
            pass
        self.assertIsNone(NPCFactory.create_npc_from_template("goblin", _BareWorld()))

    def test_unknown_template_returns_none(self):
        self.assertIsNone(NPCFactory.create_npc_from_template("totally_bogus_npc_xyz", self.world))

    def test_exception_during_construction_is_caught_and_logged(self):
        with patch("engine.npcs.npc_factory.NPC", side_effect=RuntimeError("boom")):
            result = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="factory_boom_test")
        self.assertIsNone(result)


class TestRequiredAndRandomSpells(GameTestBase):
    def test_duplicate_required_spell_ids_are_not_added_twice(self):
        self.world.npc_templates["factory_test_required_dup"] = {
            "name": "Spell Duplicate NPC",
            "properties": {"required_spells": ["magic_missile", "magic_missile"]},
        }
        npc = NPCFactory.create_npc_from_template("factory_test_required_dup", self.world, instance_id="dup_spell_npc")
        self.assertEqual(npc.usable_spells.count("magic_missile"), 1)

    def test_random_spells_with_empty_pool_learns_nothing(self):
        self.world.npc_templates["factory_test_random_empty_pool"] = {
            "name": "Empty Pool NPC",
            "properties": {"random_spells": {"pool": [], "count": [1, 1]}},
        }
        npc = NPCFactory.create_npc_from_template("factory_test_random_empty_pool", self.world, instance_id="empty_pool_npc")
        self.assertEqual(npc.usable_spells, [])

    def test_random_spells_with_zero_count_learns_nothing(self):
        self.world.npc_templates["factory_test_random_zero_count"] = {
            "name": "Zero Count NPC",
            "properties": {"random_spells": {"pool": ["magic_missile"], "count": [0, 0]}},
        }
        npc = NPCFactory.create_npc_from_template("factory_test_random_zero_count", self.world, instance_id="zero_count_npc")
        self.assertEqual(npc.usable_spells, [])


class TestInitialInventory(GameTestBase):
    def test_non_dict_item_ref_is_skipped(self):
        self.world.npc_templates["factory_test_inv_non_dict"] = {
            "name": "Bad Inventory NPC",
            "initial_inventory": ["not a dict"],
        }
        npc = NPCFactory.create_npc_from_template("factory_test_inv_non_dict", self.world, instance_id="inv_non_dict_npc")
        self.assertTrue(all(slot.item is None for slot in npc.inventory.slots))

    def test_unknown_item_template_id_is_skipped(self):
        self.world.npc_templates["factory_test_inv_unknown"] = {
            "name": "Unknown Item NPC",
            "initial_inventory": [{"item_id": "totally_bogus_item_xyz", "quantity": 1}],
        }
        npc = NPCFactory.create_npc_from_template("factory_test_inv_unknown", self.world, instance_id="inv_unknown_npc")
        self.assertIsNone(npc.inventory.find_item_by_name("totally_bogus_item_xyz"))

    def test_invalid_item_id_type_is_skipped(self):
        self.world.npc_templates["factory_test_inv_invalid_id"] = {
            "name": "Invalid Id NPC",
            "initial_inventory": [{"item_id": 12345, "quantity": 1}],
        }
        npc = NPCFactory.create_npc_from_template("factory_test_inv_invalid_id", self.world, instance_id="inv_invalid_id_npc")
        self.assertIsNotNone(npc)

    def test_multiple_valid_item_refs_are_all_added(self):
        self.world.npc_templates["factory_test_inv_multi"] = {
            "name": "Multi Item NPC",
            "initial_inventory": [
                {"item_id": "item_iron_sword", "quantity": 1},
                {"item_id": "item_healing_potion_small", "quantity": 2},
            ],
        }
        npc = NPCFactory.create_npc_from_template("factory_test_inv_multi", self.world, instance_id="inv_multi_npc")
        self.assertIsNotNone(npc.inventory.find_item_by_name("Iron Sword") or npc.inventory.find_item_by_name("sword"))

    def test_factory_creation_failure_for_a_valid_template_is_skipped(self):
        self.world.npc_templates["factory_test_inv_factory_fail"] = {
            "name": "Factory Fail NPC",
            "initial_inventory": [{"item_id": "item_iron_sword", "quantity": 1}],
        }
        with patch("engine.npcs.npc_factory.ItemFactory.create_item_from_template", return_value=None):
            npc = NPCFactory.create_npc_from_template(
                "factory_test_inv_factory_fail", self.world, instance_id="inv_factory_fail_npc",
            )
        self.assertIsNotNone(npc)
        self.assertTrue(all(slot.item is None for slot in npc.inventory.slots))

    def test_non_list_initial_inventory_logs_warning(self):
        self.world.npc_templates["factory_test_inv_non_list"] = {
            "name": "Non List Inventory NPC",
            "initial_inventory": "not a list",
        }
        npc = NPCFactory.create_npc_from_template("factory_test_inv_non_list", self.world, instance_id="inv_non_list_npc")
        self.assertIsNotNone(npc)


if __name__ == "__main__":
    unittest.main()
