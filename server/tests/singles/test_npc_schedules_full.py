# tests/singles/test_npc_schedules_full.py
"""Coverage for engine/npcs/ai/schedules.py: initialize_npc_schedules'
no-world/no-rooms guards, the missing-template_id skip, the bartender
dispatch branch, _designate_locale_spaces' duplicate-room-info skip and
direct-call fallback-with-no-rooms path, _get_random_location's empty-list
guard, and _create_merchant_schedule/_create_bartender_schedule's explicit
"region:room" work_location parsing."""

import unittest

from tests.fixtures import GameTestBase
from engine.npcs.npc import NPC
from engine.world.region import Region
from engine.world.room import Room
from engine.npcs.ai.schedules import (
    initialize_npc_schedules,
    _designate_locale_spaces,
    _get_random_location,
    _create_merchant_schedule,
    _create_bartender_schedule,
)


class TestInitializeNpcSchedulesGuards(unittest.TestCase):
    def test_no_world_is_a_noop(self):
        initialize_npc_schedules(None)  # must not raise

    def test_no_rooms_in_world_is_a_noop(self):
        class _EmptyWorld:
            regions = {}
            npcs = {}
        initialize_npc_schedules(_EmptyWorld())  # must not raise


class TestInitializeNpcSchedulesDispatch(GameTestBase):
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

    def test_bartender_template_gets_a_bartender_schedule(self):
        npc = self._add_npc("sched_bartender", "town_bartender")
        initialize_npc_schedules(self.world)
        self.assertEqual(npc.behavior_type, "scheduled")
        self.assertIn("preparing the bar", [v["activity"] for v in npc.schedule.values()])


class TestDesignateLocaleSpaces(GameTestBase):
    def test_duplicate_room_info_is_not_added_twice(self):
        # Two distinct rooms whose collected info dicts are equal by value
        # (same region/room id, name, properties) -- exercises the "already
        # present in this space_type" skip on the second insertion.
        room_info = {
            "region_id": "dup_region", "room_id": "shared_market_xyz",
            "room_name": "A Unique Market Bazaar Name Xyz", "properties": {},
        }
        available_rooms = [dict(room_info), dict(room_info)]

        town_spaces = _designate_locale_spaces(self.world, available_rooms)

        matching = [r for r in town_spaces["markets"] if r == room_info]
        self.assertEqual(len(matching), 1)

    def test_fallback_with_no_available_rooms_leaves_spaces_empty(self):
        town_spaces = _designate_locale_spaces(self.world, [])
        for space_type, rooms in town_spaces.items():
            self.assertEqual(rooms, [])


class TestGetRandomLocation(unittest.TestCase):
    def test_empty_locations_returns_none(self):
        self.assertIsNone(_get_random_location([]))


class TestMerchantAndBartenderScheduleWorkLocation(unittest.TestCase):
    def _npc(self):
        npc = NPC(obj_id="sched_probe_npc", name="Probe NPC")
        npc.home_region_id = "fallback_region"
        npc.home_room_id = "fallback_room"
        npc.properties = {}
        return npc

    def _empty_town_spaces(self):
        return {"homes": [], "shops": [], "taverns": [], "markets": [], "civic_area": [],
                "gardens": [], "work_areas": [], "social_areas": []}

    def test_merchant_explicit_work_location_is_parsed(self):
        npc = self._npc()
        npc.properties["work_location"] = "shop_region:shop_room"
        _create_merchant_schedule(npc, self._empty_town_spaces())
        opening = npc.schedule["8"]
        self.assertEqual(opening["region_id"], "shop_region")
        self.assertEqual(opening["room_id"], "shop_room")

    def test_merchant_falls_back_to_home_location_without_work_location(self):
        npc = self._npc()
        _create_merchant_schedule(npc, self._empty_town_spaces())
        opening = npc.schedule["8"]
        self.assertEqual(opening["region_id"], "fallback_region")
        self.assertEqual(opening["room_id"], "fallback_room")

    def test_bartender_explicit_work_location_is_parsed(self):
        npc = self._npc()
        npc.properties["work_location"] = "tavern_region:tavern_room"
        _create_bartender_schedule(npc, self._empty_town_spaces())
        working = npc.schedule["14"]
        self.assertEqual(working["region_id"], "tavern_region")
        self.assertEqual(working["room_id"], "tavern_room")

    def test_bartender_falls_back_to_home_location_without_work_location(self):
        npc = self._npc()
        _create_bartender_schedule(npc, self._empty_town_spaces())
        working = npc.schedule["14"]
        self.assertEqual(working["region_id"], "fallback_region")
        self.assertEqual(working["room_id"], "fallback_room")


if __name__ == "__main__":
    unittest.main()
