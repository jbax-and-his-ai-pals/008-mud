# tests/singles/test_quest_objectives_full.py
"""Direct coverage for engine/core/quest_generation/objectives.py's three
generator functions, including their "no valid candidates" None-returning
branches, which the generator-level tests (test_quest_generator.py) mock
around rather than exercise."""

import unittest

from engine.core.quest_generation.objectives import (
    generate_kill_objective, generate_fetch_objective, generate_deliver_objective,
)


class _FakeRegion:
    def __init__(self, name):
        self.name = name


class _FakeNPC:
    def __init__(self, obj_id="giver", region_id=None, faction="neutral", name="Giver", is_alive=True):
        self.obj_id = obj_id
        self.current_region_id = region_id
        self.faction = faction
        self.name = name
        self.is_alive = is_alive


class _FakeWorld:
    def __init__(self):
        self.npc_templates = {}
        self.item_templates = {}
        self.npcs = {}
        self.regions = {}

    def get_region(self, region_id):
        return self.regions.get(region_id)


class TestGenerateKillObjective(unittest.TestCase):
    def test_no_valid_targets_returns_none(self):
        world = _FakeWorld()
        giver = _FakeNPC()
        self.assertIsNone(generate_kill_objective(world, 1, giver, {}))

    def test_with_giver_region_includes_region_name_in_hint(self):
        world = _FakeWorld()
        world.npc_templates["goblin"] = {"faction": "hostile", "level": 1, "name": "Goblin"}
        world.regions["town"] = _FakeRegion("Town")
        giver = _FakeNPC(region_id="town")
        result = generate_kill_objective(world, 1, giver, {})
        self.assertIsNotNone(result)
        self.assertIn("Town", result["location_hint"])

    def test_without_giver_region_uses_generic_hint(self):
        world = _FakeWorld()
        world.npc_templates["goblin"] = {"faction": "hostile", "level": 1, "name": "Goblin"}
        giver = _FakeNPC(region_id=None)
        result = generate_kill_objective(world, 1, giver, {})
        self.assertEqual("nearby regions", result["location_hint"])


class TestGenerateFetchObjective(unittest.TestCase):
    def test_no_valid_options_returns_none(self):
        world = _FakeWorld()
        giver = _FakeNPC()
        self.assertIsNone(generate_fetch_objective(world, 1, giver, {}))

    def test_key_type_items_are_excluded(self):
        world = _FakeWorld()
        world.item_templates["item_key"] = {"type": "Key", "name": "Key"}
        world.npc_templates["goblin"] = {
            "faction": "hostile", "level": 1, "name": "Goblin", "loot_table": {"item_key": 0.5},
        }
        giver = _FakeNPC()
        self.assertIsNone(generate_fetch_objective(world, 1, giver, {}))

    def test_procedural_template_display_name_is_excluded(self):
        world = _FakeWorld()
        world.item_templates["item_random_scroll"] = {
            "type": "Consumable", "name": "Scroll of {spell_name}", "value": 100,
        }
        world.npc_templates["goblin"] = {
            "faction": "hostile", "level": 1, "name": "Goblin",
            "loot_table": {"item_random_scroll": 0.5},
        }
        self.assertIsNone(generate_fetch_objective(world, 1, _FakeNPC(), {}))

    def test_valid_option_builds_objective(self):
        world = _FakeWorld()
        world.item_templates["item_widget"] = {"type": "Misc", "name": "Widget", "value": 10}
        world.npc_templates["goblin"] = {
            "faction": "hostile", "level": 1, "name": "Goblin", "loot_table": {"item_widget": 0.5},
        }
        giver = _FakeNPC()
        result = generate_fetch_objective(world, 1, giver, {})
        self.assertEqual("item_widget", result["item_id"])
        self.assertIn("Goblin", result["source_enemy_name_plural"])
        self.assertEqual(1, result["difficulty_level"])


class TestGenerateDeliverObjective(unittest.TestCase):
    def test_no_recipients_returns_none(self):
        world = _FakeWorld()
        giver = _FakeNPC(obj_id="giver_1")
        self.assertIsNone(generate_deliver_objective(world, 1, giver, {}))

    def test_no_package_template_returns_none(self):
        world = _FakeWorld()
        recipient = _FakeNPC(obj_id="recipient_1", faction="neutral", is_alive=True)
        world.npcs["recipient_1"] = recipient
        giver = _FakeNPC(obj_id="giver_1")
        self.assertIsNone(generate_deliver_objective(world, 1, giver, {}))

    def test_successful_generation_with_region(self):
        world = _FakeWorld()
        world.item_templates["quest_package_generic"] = {"name": "Package"}
        world.regions["town"] = _FakeRegion("Town")
        recipient = _FakeNPC(obj_id="recipient_1", region_id="town", faction="neutral", name="Recipient")
        world.npcs["recipient_1"] = recipient
        giver = _FakeNPC(obj_id="giver_1", name="Giver")
        result = generate_deliver_objective(world, 1, giver, {})
        self.assertEqual("recipient_1", result["recipient_instance_id"])
        self.assertEqual("Town", result["recipient_location_description"])

    def test_recipient_without_region_uses_unknown(self):
        world = _FakeWorld()
        world.item_templates["quest_package_generic"] = {"name": "Package"}
        recipient = _FakeNPC(obj_id="recipient_1", region_id=None, faction="neutral")
        world.npcs["recipient_1"] = recipient
        giver = _FakeNPC(obj_id="giver_1")
        result = generate_deliver_objective(world, 1, giver, {})
        self.assertEqual("Unknown", result["recipient_location_description"])

    def test_hostile_and_self_recipients_are_excluded(self):
        world = _FakeWorld()
        world.item_templates["quest_package_generic"] = {"name": "Package"}
        hostile = _FakeNPC(obj_id="hostile_1", faction="hostile")
        world.npcs["hostile_1"] = hostile
        giver = _FakeNPC(obj_id="giver_1")
        world.npcs["giver_1"] = giver  # giver is present but must be excluded as its own recipient
        self.assertIsNone(generate_deliver_objective(world, 1, giver, {}))


if __name__ == "__main__":
    unittest.main()
