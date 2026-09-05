# tests/singles/test_room_full.py
"""Coverage for engine/world/room.py: update()'s environmental-effect revert
branches, apply_elemental_interaction()'s action dispatch, apply_hazards()'s
dead/no-hazard/cooldown/damage branches, get_full_description()'s neutral
temperature branch, and remove_item/get_item's found/missing paths."""

import unittest

from engine.items.item import Item
from engine.world.room import Room


class _FakeEntity:
    def __init__(self, obj_id="fake_entity", alive=True, damage_taken=5):
        self.obj_id = obj_id
        self.is_alive = alive
        self._damage_taken = damage_taken
        self.damage_calls = []

    def take_damage(self, amount, damage_type):
        self.damage_calls.append((amount, damage_type))
        return self._damage_taken


class TestRoomUpdate(unittest.TestCase):
    def setUp(self):
        self.room = Room("Test Room", "A room.", obj_id="test_room")

    def test_no_active_effects_returns_empty_immediately(self):
        self.assertEqual(self.room.update(1.0), [])

    def test_effect_not_yet_expired_stays_active_with_no_message(self):
        self.room.active_env_effects = [{
            "action": "modify_exit_req", "direction": "north",
            "original_value": None, "time_remaining": 10.0,
        }]
        messages = self.room.update(1.0)
        self.assertEqual(messages, [])
        self.assertEqual(len(self.room.active_env_effects), 1)
        self.assertAlmostEqual(self.room.active_env_effects[0]["time_remaining"], 9.0)

    def test_expired_modify_exit_req_with_no_prior_value_deletes_requirement(self):
        self.room.properties["exit_requirements"] = {"north": "key_gate"}
        self.room.active_env_effects = [{
            "action": "modify_exit_req", "direction": "north",
            "original_value": None, "time_remaining": 0.5,
        }]
        messages = self.room.update(1.0)
        self.assertNotIn("north", self.room.properties["exit_requirements"])
        self.assertIn("returns to normal", messages[0])
        self.assertEqual(self.room.active_env_effects, [])

    def test_expired_modify_exit_req_restores_prior_value(self):
        self.room.properties["exit_requirements"] = {"north": "temp_cleared"}
        self.room.active_env_effects = [{
            "action": "modify_exit_req", "direction": "north",
            "original_value": "locked", "time_remaining": 0.5,
        }]
        self.room.update(1.0)
        self.assertEqual(self.room.properties["exit_requirements"]["north"], "locked")

    def test_expired_suppress_hazard_restores_hazard_type(self):
        self.room.active_env_effects = [{
            "action": "suppress_hazard", "original_value": "fire",
            "time_remaining": 0.5,
        }]
        messages = self.room.update(1.0)
        self.assertEqual(self.room.properties.get("hazard_type"), "fire")
        self.assertIn("hazard returns", messages[0])

    def test_expired_effect_with_unrecognized_action_produces_no_message(self):
        self.room.active_env_effects = [{
            "action": "something_unhandled", "time_remaining": 0.5,
        }]
        messages = self.room.update(1.0)
        self.assertEqual(messages, [])
        self.assertEqual(self.room.active_env_effects, [])


class TestApplyElementalInteraction(unittest.TestCase):
    def setUp(self):
        self.room = Room("Test Room", "A room.", obj_id="test_room")

    def test_no_interactions_returns_none(self):
        self.assertIsNone(self.room.apply_elemental_interaction("fire"))

    def test_no_matching_reaction_returns_none(self):
        self.room.properties["env_interactions"] = {"ice": {"type": "clear_exit_req"}}
        self.assertIsNone(self.room.apply_elemental_interaction("fire"))

    def test_clear_exit_req_with_matching_direction_applies_and_returns_message(self):
        self.room.properties["exit_requirements"] = {"north": "locked"}
        self.room.properties["env_interactions"] = {
            "fire": {"type": "clear_exit_req", "direction": "north", "duration": 5.0, "message": "The ice melts."}
        }
        result = self.room.apply_elemental_interaction("fire")
        self.assertIn("melts", result)
        self.assertNotIn("north", self.room.properties["exit_requirements"])
        self.assertEqual(len(self.room.active_env_effects), 1)
        self.assertEqual(self.room.active_env_effects[0]["original_value"], "locked")

    def test_clear_exit_req_with_direction_not_in_requirements_returns_none(self):
        self.room.properties["exit_requirements"] = {}
        self.room.properties["env_interactions"] = {
            "fire": {"type": "clear_exit_req", "direction": "north"}
        }
        self.assertIsNone(self.room.apply_elemental_interaction("fire"))

    def test_suppress_hazard_with_active_hazard_applies_and_returns_message(self):
        self.room.properties["hazard_type"] = "poison"
        self.room.properties["env_interactions"] = {
            "water": {"type": "suppress_hazard", "duration": 5.0, "message": "The poison is washed away."}
        }
        result = self.room.apply_elemental_interaction("water")
        self.assertIn("washed away", result)
        self.assertIsNone(self.room.properties.get("hazard_type"))
        self.assertEqual(self.room.active_env_effects[0]["original_value"], "poison")

    def test_suppress_hazard_with_no_active_hazard_returns_none(self):
        self.room.properties["env_interactions"] = {
            "water": {"type": "suppress_hazard"}
        }
        self.assertIsNone(self.room.apply_elemental_interaction("water"))

    def test_unrecognized_action_returns_none(self):
        self.room.properties["env_interactions"] = {
            "fire": {"type": "something_unhandled"}
        }
        self.assertIsNone(self.room.apply_elemental_interaction("fire"))


class TestApplyHazards(unittest.TestCase):
    def setUp(self):
        self.room = Room("Hazard Room", "A room.", obj_id="hazard_room")

    def test_dead_entity_returns_none(self):
        entity = _FakeEntity(alive=False)
        self.assertIsNone(self.room.apply_hazards(entity, 100.0))

    def test_no_hazard_type_returns_none(self):
        entity = _FakeEntity()
        self.assertIsNone(self.room.apply_hazards(entity, 100.0))

    def test_cooldown_not_elapsed_returns_none(self):
        self.room.properties["hazard_type"] = "fire"
        self.room.properties["hazard_tick_interval"] = 3.0
        entity = _FakeEntity(obj_id="e_cd")
        self.room.apply_hazards(entity, 100.0)
        result = self.room.apply_hazards(entity, 101.0)
        self.assertIsNone(result)
        self.assertEqual(len(entity.damage_calls), 1)

    def test_entity_without_obj_id_skips_cooldown_tracking(self):
        self.room.properties["hazard_type"] = "fire"

        class _NoIdEntity:
            is_alive = True
            def take_damage(self, amount, damage_type):
                return amount

        entity = _NoIdEntity()
        result = self.room.apply_hazards(entity, 100.0)
        self.assertIsNotNone(result)

    def test_damage_taken_produces_flavor_message(self):
        self.room.properties["hazard_type"] = "fire"
        self.room.properties["hazard_damage"] = 7
        entity = _FakeEntity(obj_id="e_dmg", damage_taken=7)
        result = self.room.apply_hazards(entity, 100.0)
        self.assertIsNotNone(result)
        self.assertIn("-7 HP", result)
        self.assertEqual(entity.damage_calls[0][0], 7)

    def test_zero_damage_taken_returns_none(self):
        self.room.properties["hazard_type"] = "fire"
        entity = _FakeEntity(obj_id="e_zero", damage_taken=0)
        result = self.room.apply_hazards(entity, 100.0)
        self.assertIsNone(result)


class TestGetFullDescriptionNeutralTemperature(unittest.TestCase):
    def test_normal_temperature_adds_no_temperature_line(self):
        room = Room("Neutral Room", "A plain room.", obj_id="neutral_room")
        room.properties["temperature"] = "normal"
        desc = room.get_full_description()
        self.assertNotIn("cold", desc)
        self.assertNotIn("stiflingly hot", desc)
        self.assertIn("Exits:", desc)

    def test_cold_temperature_adds_cold_line(self):
        room = Room("Cold Room", "A plain room.", obj_id="cold_room")
        room.properties["temperature"] = "cold"
        desc = room.get_full_description()
        self.assertIn("noticeably cold", desc)


class TestRemoveAndGetItem(unittest.TestCase):
    def setUp(self):
        self.room = Room("Item Room", "A room.", obj_id="item_room")
        self.item = Item(obj_id="test_item", name="Test Item")
        self.room.add_item(self.item)

    def test_remove_item_not_found_returns_none(self):
        self.assertIsNone(self.room.remove_item("nonexistent_item"))

    def test_remove_item_found_removes_and_returns_it(self):
        removed = self.room.remove_item("test_item")
        self.assertIs(removed, self.item)
        self.assertNotIn(self.item, self.room.items)

    def test_get_item_not_found_returns_none(self):
        self.assertIsNone(self.room.get_item("nonexistent_item"))

    def test_get_item_found_returns_it_without_removing(self):
        found = self.room.get_item("test_item")
        self.assertIs(found, self.item)
        self.assertIn(self.item, self.room.items)


if __name__ == "__main__":
    unittest.main()
