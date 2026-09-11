# tests/singles/test_districts.py
"""Coverage for the district-as-identity feature: World.get_district,
the room-header display, and the residential district's non-directional
gate. Districts have no mechanical behavior of their own -- this is
purely a lookup and a display, plus the content sanity that the
reference-integrity validator doesn't check (districts aren't item/quest
references)."""

from tests.fixtures import GameTestBase


class TestDistrictContent(GameTestBase):
    def test_every_district_room_resolves_to_a_real_room(self):
        region = self.world.get_region("town")
        districts = region.properties.get("districts", {})
        self.assertTrue(districts)
        for district_id, district in districts.items():
            for room_id in district["rooms"]:
                self.assertIsNotNone(
                    region.get_room(room_id),
                    f"district '{district_id}' references missing room '{room_id}'",
                )


class TestGetDistrict(GameTestBase):
    def test_room_inside_a_district_returns_it(self):
        district = self.world.get_district("town", "residential_street_east")
        self.assertIsNotNone(district)
        self.assertEqual("Residential District", district["name"])

    def test_room_outside_any_district_returns_none(self):
        self.assertIsNone(self.world.get_district("town", "town_square"))

    def test_unknown_region_or_room_returns_none(self):
        self.assertIsNone(self.world.get_district("nonexistent_region", "residential_street_east"))
        self.assertIsNone(self.world.get_district("town", "nonexistent_room"))
        self.assertIsNone(self.world.get_district(None, None))


class TestDistrictHeaderDisplay(GameTestBase):
    def test_header_shows_district_name_inside_it(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "residential_street_east"
        result = self.game.process_command("look")
        self.assertIn("RESIDENTIAL DISTRICT", result)

    def test_header_omits_district_outside_it(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        result = self.game.process_command("look")
        self.assertNotIn("DISTRICT", result)


class TestResidentialGate(GameTestBase):
    def test_entering_the_district_via_the_gate(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "west_lane"
        result = self.game.process_command("in")
        self.assertEqual("residential_street_east", self.player.current_room_id)
        self.assertIn("RESIDENTIAL DISTRICT", result)

    def test_leaving_the_district_via_the_gate(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "residential_street_east"
        result = self.game.process_command("out")
        self.assertEqual("west_lane", self.player.current_room_id)
        self.assertNotIn("DISTRICT", result)

    def test_old_compass_directions_no_longer_connect_them(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "west_lane"
        result = self.game.process_command("west")
        self.assertEqual("west_lane", self.player.current_room_id)
        self.assertIn("cannot go", result.lower())

        self.player.current_room_id = "residential_street_east"
        result = self.game.process_command("east")
        self.assertEqual("residential_street_east", self.player.current_room_id)
        self.assertIn("cannot go", result.lower())
