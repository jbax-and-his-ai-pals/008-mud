# tests/singles/test_env_deviation_chain.py
"""Coverage for World.get_env_property's room -> district -> region
deviation chain (dark/noisy/smell/temperature and friends): a room only
needs to author a value when it departs from its district's or region's
norm, instead of every room repeating the same tag. Also covers the
get_district() fix that let this chain's district tier work at all --
it only ever matched a "rooms" key, while authored content (and the
editor) uses "members"."""
from tests.fixtures import GameTestBase
from engine.world.room import Room


class TestEnvDeviationChain(GameTestBase):
    def setUp(self):
        super().setUp()
        self.region = self.world.get_region("town")
        self.region.properties.setdefault("districts", {})
        self.region.properties["districts"]["_test_district"] = {
            "name": "Test District",
            "members": ["_district_room"],
        }
        district_room = Room("District Room", "A room in a district.", obj_id="_district_room")
        self.region.add_room("_district_room", district_room)
        plain_room = Room("Plain Room", "A room with no district.", obj_id="_plain_room")
        self.region.add_room("_plain_room", plain_room)

    def test_room_setting_wins_over_district_and_region(self):
        self.region.properties["dark"] = True
        self.region.properties["districts"]["_test_district"]["dark"] = True
        room = self.region.get_room("_district_room")
        room.properties["dark"] = False
        self.assertFalse(self.world.get_env_property("town", "_district_room", "dark", False))

    def test_district_setting_wins_over_region_when_room_is_silent(self):
        self.region.properties["dark"] = False
        self.region.properties["districts"]["_test_district"]["dark"] = True
        self.assertTrue(self.world.get_env_property("town", "_district_room", "dark", False))

    def test_region_setting_applies_when_room_has_no_district(self):
        self.region.properties["dark"] = True
        self.assertTrue(self.world.get_env_property("town", "_plain_room", "dark", False))

    def test_default_applies_when_nothing_in_the_chain_sets_it(self):
        self.assertEqual("normal", self.world.get_env_property("town", "_plain_room", "temperature", "normal"))

    def test_district_lookup_matches_members_key_not_just_rooms(self):
        # get_district() historically only checked district["rooms"], so a
        # district authored with "members" (the editor's convention) never
        # resolved -- the district tier of the chain silently never fired.
        district = self.world.get_district("town", "_district_room")
        self.assertIsNotNone(district)
        self.assertEqual("Test District", district["name"])


class TestCavesRegionDarkDefault(GameTestBase):
    """Regression coverage for the caves.json migration: nearly every room
    was individually authored "dark": true; it's now a single region-level
    default with four rooms (the lit exceptions) overriding it to false."""

    def test_a_room_with_no_local_dark_inherits_the_region_default(self):
        self.player.current_region_id = "caves"
        self.player.current_room_id = "main_cavern"
        desc = self.world.look()
        self.assertIn("very dark", desc)

    def test_an_explicitly_lit_room_overrides_the_region_default(self):
        self.player.current_region_id = "caves"
        self.player.current_room_id = "crystal_chamber"
        desc = self.world.look()
        self.assertNotIn("very dark", desc)
