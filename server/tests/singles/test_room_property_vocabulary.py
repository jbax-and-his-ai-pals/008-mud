"""The room property vocabulary is what the engine (and the editor) read.

`ROOM_PROPERTY_KINDS` lists the room `properties` the engine reads; the
validator warns about any other key, so each listed key must really have a
reader, or a key that does nothing would pass as known. `ROOM_EDITOR_PROPERTY_KINDS`
lists the world editor's own map keys.
"""
import re
import unittest
from pathlib import Path

from engine.world.room import ROOM_EDITOR_PROPERTY_KINDS, ROOM_PROPERTY_KINDS

REPO = Path(__file__).resolve().parents[3]
ENGINE = REPO / "server" / "engine"
EDITOR = REPO / "mud-world-editor" / "scripts"

# Keys whose only reader is the content validator itself: a declaration about
# the room rather than a runtime behaviour.
VALIDATOR_DECLARATIONS = {"entered_by_system"}


def _sources(root: Path, pattern: str, skip: tuple = ()) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob(pattern) if path.name not in skip
    )


class TestRoomPropertyVocabulary(unittest.TestCase):
    def test_every_engine_key_has_a_reader_outside_the_validator(self):
        source = _sources(ENGINE, "*.py", skip=("content_set.py", "room.py"))
        room_source = (ENGINE / "world" / "room.py").read_text(encoding="utf-8")
        room_body = room_source.split("class Room", 1)[1]
        for key in ROOM_PROPERTY_KINDS:
            if key in VALIDATOR_DECLARATIONS:
                continue
            read = re.search(r'[\'"]%s[\'"]' % re.escape(key), source) or re.search(r'[\'"]%s[\'"]' % re.escape(key), room_body)
            self.assertTrue(read, f"room property '{key}' is listed as read, but nothing in the engine names it")

    def test_every_editor_key_is_read_by_the_editor(self):
        source = _sources(EDITOR, "*.gd", skip=("RoomPropertiesPanel.gd",))
        for key in ROOM_EDITOR_PROPERTY_KINDS:
            self.assertRegex(source, r'"%s"' % re.escape(key), f"editor room key '{key}' is read by nothing in the editor")

    def test_the_retired_keys_are_not_known(self):
        # `indoors`, `underwater` and `music` were authored or offered, and nothing read them.
        for key in ("indoors", "underwater", "music"):
            self.assertNotIn(key, ROOM_PROPERTY_KINDS)
            self.assertNotIn(key, ROOM_EDITOR_PROPERTY_KINDS)


class TestRegionAndDistrictVocabulary(unittest.TestCase):
    """The same promise for `region.py`'s REGION_PROPERTY_KINDS and
    DISTRICT_PROPERTY_KINDS: each listed key has a reader."""

    # Read only by the validator's classification policy (ruleset.world.regions).
    CLASSIFICATION = {"biome", "region_type"}

    def test_every_region_and_district_key_has_a_reader(self):
        from engine.world.region import DISTRICT_PROPERTY_KINDS, REGION_PROPERTY_KINDS

        source = _sources(ENGINE, "*.py", skip=("content_set.py", "region.py"))
        # region.py itself counts, past the constants that list the keys.
        source += (ENGINE / "world" / "region.py").read_text(encoding="utf-8").split("class Region", 1)[1]
        for key in {**REGION_PROPERTY_KINDS, **DISTRICT_PROPERTY_KINDS}:
            if key in self.CLASSIFICATION:
                continue
            self.assertRegex(source, r'[\'"]%s[\'"]' % re.escape(key), f"'{key}' is listed as read, but nothing in the engine names it")

    def test_retired_region_keys_are_not_known(self):
        from engine.world.region import DISTRICT_PROPERTY_KINDS, REGION_PROPERTY_KINDS

        for key in ("indoors", "weather", "music", "spawn_templates", "spawn_level_range"):
            self.assertNotIn(key, REGION_PROPERTY_KINDS)
            self.assertNotIn(key, DISTRICT_PROPERTY_KINDS)


class TestIndoorRoomsAreIndoors(unittest.TestCase):
    """fantasy_frontier authored `"indoors": true`, which nothing read; with
    `outdoors` unset the room fell through to its region and counted as
    outdoors, so the auction hall had weather. They now say `outdoors: false`."""

    def test_the_converted_rooms_are_not_outdoors(self):
        from engine.server.headless_server import HeadlessServer

        server = HeadlessServer(db_path=":memory:", content_set_path=str(REPO / "content_sets" / "fantasy_frontier"))
        for region_id, room_id in (("aurelia_city", "auction_hall"), ("frostpeak_outpost", "bunkhouse"), ("casino", None)):
            rooms = [room_id] if room_id else list(server.world.get_region(region_id).rooms)[:1]
            for room in rooms:
                self.assertFalse(server.world.is_location_outdoors(region_id, room), (region_id, room))


if __name__ == "__main__":
    unittest.main()
