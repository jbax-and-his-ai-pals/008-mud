# tests/singles/test_npc_schedules_full.py
"""Coverage for engine/npcs/ai/schedules.py.

This module has no built-in vocabulary of its own (no "merchant", no
"tavern") -- everything comes from a content set's "npc_schedules" ruleset
section, resolved through a small generic location-slot DSL (self /
property_or_self / category). These tests exercise that generic mechanism
directly with synthetic, non-thematic role configs, plus one integration
test confirming fantasy_frontier's real ruleset still produces working
schedules end to end."""

import unittest

from tests.fixtures import GameTestBase
from engine.npcs.npc import NPC
from engine.npcs.ai.schedules import (
    initialize_npc_schedules,
    _match_role,
    _designate_locale_spaces,
    _get_random_location,
    _resolve_slot,
    _build_schedule,
)


class TestInitializeNpcSchedulesGuards(unittest.TestCase):
    def test_no_world_is_a_noop(self):
        initialize_npc_schedules(None)  # must not raise

    def test_missing_ruleset_section_is_a_noop(self):
        class _World:
            def ruleset_section(self, name):
                return {}
        initialize_npc_schedules(_World())  # must not raise

    def test_roles_configured_but_no_rooms_is_a_noop(self):
        class _World:
            regions = {}
            npcs = {}
            def ruleset_section(self, name):
                return {"roles": [{"id": "worker", "template_keywords": ["worker"]}]}
        initialize_npc_schedules(_World())  # must not raise


class TestInitializeNpcSchedulesDispatch(GameTestBase):
    """Integration coverage using fantasy_frontier's real npc_schedules ruleset."""

    def _add_npc(self, instance_id, template_id, name="Test NPC"):
        npc = NPC(obj_id=instance_id, name=name)
        npc.template_id = template_id
        npc.faction = "neutral"
        npc.home_region_id = self.player.current_region_id
        npc.home_room_id = self.player.current_room_id
        self.world.npcs[instance_id] = npc
        return npc

    def test_npc_without_template_id_is_skipped(self):
        npc = self._add_npc("sched_no_template", None)
        npc.template_id = None
        initialize_npc_schedules(self.world)
        self.assertNotEqual(getattr(npc, "behavior_type", None), "scheduled")

    def test_npc_with_unmatched_template_is_skipped(self):
        npc = self._add_npc("sched_unmatched", "totally_unrelated_thing")
        initialize_npc_schedules(self.world)
        self.assertNotEqual(getattr(npc, "behavior_type", None), "scheduled")

    def test_excluded_name_keyword_is_skipped_even_if_role_matches(self):
        npc = self._add_npc("sched_guard_merchant", "town_merchant", name="Merchant Guard")
        initialize_npc_schedules(self.world)
        self.assertNotEqual(getattr(npc, "behavior_type", None), "scheduled")

    def test_bartender_template_gets_a_bartender_schedule(self):
        npc = self._add_npc("sched_bartender", "town_bartender")
        initialize_npc_schedules(self.world)
        self.assertEqual(npc.behavior_type, "scheduled")
        self.assertIn("preparing the bar", [v["activity"] for v in npc.schedule.values()])


class TestMatchRole(unittest.TestCase):
    def test_matches_role_by_template_keyword(self):
        roles = [
            {"id": "clerk", "template_keywords": ["clerk", "cashier"]},
            {"id": "pilot", "template_keywords": ["pilot"]},
        ]
        self.assertEqual(_match_role("space_pilot_01", roles)["id"], "pilot")
        self.assertEqual(_match_role("night_clerk", roles)["id"], "clerk")

    def test_no_match_returns_none(self):
        roles = [{"id": "clerk", "template_keywords": ["clerk"]}]
        self.assertIsNone(_match_role("robot_dog", roles))


class TestDesignateLocaleSpaces(unittest.TestCase):
    def _rooms(self):
        return [
            {"region_id": "r", "room_id": "office_1", "room_name": "Corner Office", "properties": {}},
            {"region_id": "r", "room_id": "plaza_1", "room_name": "Central Plaza", "properties": {}},
            {"region_id": "r", "room_id": "empty_1", "room_name": "Nondescript Hallway", "properties": {}},
        ]

    def test_rooms_are_bucketed_by_keyword(self):
        categories = {"offices": ["office"], "civic_area": ["plaza"]}
        spaces = _designate_locale_spaces(self._rooms(), categories)
        self.assertEqual([r["room_id"] for r in spaces["offices"]], ["office_1"])
        self.assertEqual([r["room_id"] for r in spaces["civic_area"]], ["plaza_1"])

    def test_duplicate_room_info_is_not_added_twice(self):
        room_info = {"region_id": "r", "room_id": "dup", "room_name": "The Office Annex", "properties": {}}
        spaces = _designate_locale_spaces([dict(room_info), dict(room_info)], {"offices": ["office"]})
        self.assertEqual(spaces["offices"].count(room_info), 1)

    def test_unmatched_category_falls_back_to_civic_area(self):
        categories = {"offices": ["office"], "civic_area": ["plaza"], "gyms": ["gym"]}
        spaces = _designate_locale_spaces(self._rooms(), categories)
        self.assertEqual(spaces["gyms"], spaces["civic_area"])

    def test_no_available_rooms_leaves_every_category_empty(self):
        spaces = _designate_locale_spaces([], {"offices": ["office"], "civic_area": ["plaza"]})
        for rooms in spaces.values():
            self.assertEqual(rooms, [])


class TestGetRandomLocation(unittest.TestCase):
    def test_empty_locations_returns_none(self):
        self.assertIsNone(_get_random_location([]))

    def test_excludes_given_location_when_alternatives_exist(self):
        a, b = {"room_id": "a"}, {"room_id": "b"}
        self.assertEqual(_get_random_location([a], exclude_loc=None), a)
        for _ in range(10):
            self.assertEqual(_get_random_location([a, b], exclude_loc=a), b)

    def test_falls_back_to_excluded_location_when_no_alternative(self):
        a = {"room_id": "a"}
        self.assertEqual(_get_random_location([a], exclude_loc=a), a)


class TestResolveSlot(unittest.TestCase):
    def _npc(self):
        npc = NPC(obj_id="probe", name="Probe")
        npc.home_region_id = "fallback_region"
        npc.home_room_id = "fallback_room"
        npc.properties = {}
        return npc

    def test_self_type_returns_npc_home(self):
        npc = self._npc()
        loc = _resolve_slot(npc, {"type": "self"}, {}, {})
        self.assertEqual(loc, {"region_id": "fallback_region", "room_id": "fallback_room"})

    def test_property_or_self_parses_region_room_property(self):
        npc = self._npc()
        npc.properties["work_location"] = "office_region:office_room"
        loc = _resolve_slot(npc, {"type": "property_or_self", "property": "work_location"}, {}, {})
        self.assertEqual(loc, {"region_id": "office_region", "room_id": "office_room"})

    def test_property_or_self_falls_back_to_self_when_property_missing(self):
        npc = self._npc()
        loc = _resolve_slot(npc, {"type": "property_or_self", "property": "work_location"}, {}, {})
        self.assertEqual(loc, {"region_id": "fallback_region", "room_id": "fallback_room"})

    def test_property_or_self_falls_back_to_self_when_property_malformed(self):
        npc = self._npc()
        npc.properties["work_location"] = "no_colon_here"
        loc = _resolve_slot(npc, {"type": "property_or_self", "property": "work_location"}, {}, {})
        self.assertEqual(loc, {"region_id": "fallback_region", "room_id": "fallback_room"})

    def test_category_type_picks_from_locale_spaces(self):
        npc = self._npc()
        office = {"region_id": "r", "room_id": "office_1"}
        locale_spaces = {"offices": [office]}
        loc = _resolve_slot(npc, {"type": "category", "categories": ["offices"]}, locale_spaces, {})
        self.assertEqual(loc, office)

    def test_category_type_excludes_already_resolved_slot(self):
        npc = self._npc()
        office_a = {"region_id": "r", "room_id": "office_a"}
        office_b = {"region_id": "r", "room_id": "office_b"}
        locale_spaces = {"offices": [office_a, office_b]}
        resolved = {"home": office_a}
        for _ in range(10):
            loc = _resolve_slot(npc, {"type": "category", "categories": ["offices"], "exclude": "home"}, locale_spaces, resolved)
            self.assertEqual(loc, office_b)

    def test_category_type_falls_back_to_named_slot_when_empty(self):
        npc = self._npc()
        home = {"region_id": "r", "room_id": "home_1"}
        resolved = {"home": home}
        loc = _resolve_slot(npc, {"type": "category", "categories": ["offices"], "fallback": "home"}, {}, resolved)
        self.assertEqual(loc, home)

    def test_category_type_falls_back_to_self_when_empty_and_no_fallback(self):
        npc = self._npc()
        loc = _resolve_slot(npc, {"type": "category", "categories": ["offices"]}, {}, {})
        self.assertEqual(loc, {"region_id": "fallback_region", "room_id": "fallback_room"})

    def test_unknown_slot_type_falls_back_to_self(self):
        npc = self._npc()
        loc = _resolve_slot(npc, {"type": "teleport"}, {}, {})
        self.assertEqual(loc, {"region_id": "fallback_region", "room_id": "fallback_room"})


class TestBuildSchedule(unittest.TestCase):
    def test_generic_role_produces_a_schedule_with_no_thematic_vocabulary(self):
        npc = NPC(obj_id="probe2", name="Probe2")
        npc.home_region_id = "fallback_region"
        npc.home_room_id = "fallback_room"
        npc.properties = {"work_location": "office_region:office_room"}

        role = {
            "id": "clerk",
            "location_slots": {
                "work": {"type": "property_or_self", "property": "work_location"},
                "home": {"type": "self"},
            },
            "schedule": {
                "9": {"activity": "clocking in", "slot": "work"},
                "17": {"activity": "clocking out", "slot": "home"},
            },
        }

        schedule = _build_schedule(npc, role, {})

        self.assertEqual(schedule["9"]["activity"], "clocking in")
        self.assertEqual(schedule["9"]["region_id"], "office_region")
        self.assertEqual(schedule["17"]["activity"], "clocking out")
        self.assertEqual(schedule["17"]["region_id"], "fallback_region")

    def test_missing_slot_reference_falls_back_to_npc_home(self):
        npc = NPC(obj_id="probe3", name="Probe3")
        npc.home_region_id = "fallback_region"
        npc.home_room_id = "fallback_room"
        npc.properties = {}

        role = {"location_slots": {}, "schedule": {"12": {"activity": "idling", "slot": "nonexistent"}}}
        schedule = _build_schedule(npc, role, {})

        self.assertEqual(schedule["12"], {"activity": "idling", "region_id": "fallback_region", "room_id": "fallback_room"})


if __name__ == "__main__":
    unittest.main()
