# tests/singles/test_save_declares_restored_keys.py
"""A snapshot says what it carries and what it leaves out, and the two lists are true.

Track C's audit found the save path kept whatever it happened to keep: nothing named
the state a save was meant to restore, so nothing noticed when a piece of it (a room's
exits) was never saved at all. `world_snapshot.RESTORED` and `DROPPED` are that
declaration; these tests hold it against the code that writes and reads the snapshot.
"""

import json

from engine.world import world_snapshot
from tests.fixtures import GameTestBase


class TestSaveDeclaresRestoredKeys(GameTestBase):
    def test_a_snapshot_carries_exactly_the_sections_it_declares(self):
        snapshot = world_snapshot.capture(self.world)
        self.assertEqual(set(world_snapshot.RESTORED), set(snapshot))

    def test_a_snapshot_is_plain_json(self):
        snapshot = world_snapshot.capture(self.world)
        self.assertEqual(snapshot, json.loads(json.dumps(snapshot)))

    def test_every_dropped_thing_has_a_reason(self):
        self.assertTrue(world_snapshot.DROPPED)
        for what, why in world_snapshot.DROPPED.items():
            with self.subTest(what=what):
                self.assertTrue(isinstance(why, str) and len(why) > 20, "%r needs a reason a reader can act on" % what)

    def test_the_dropped_list_does_not_name_a_section_it_also_carries(self):
        self.assertFalse(set(world_snapshot.RESTORED) & set(world_snapshot.DROPPED))

    def test_restoring_an_empty_snapshot_does_not_raise_and_leaves_rooms_as_content_built(self):
        before = world_snapshot.capture(self.world)
        report = world_snapshot.restore(self.world, {})
        self.assertTrue(report.clean)
        self.assertEqual(before["rooms"], world_snapshot.capture(self.world)["rooms"])

    def test_a_snapshot_that_names_a_room_or_npc_content_no_longer_has_skips_it(self):
        snapshot = world_snapshot.capture(self.world)
        snapshot["rooms"]["ghost_region:ghost_room"] = {"visited": True}
        snapshot["npcs"]["ghost_npc"] = {"template_id": "a_template_content_removed", "name": "Ghost"}
        snapshot["regions"]["ghost_region"] = {"set": {"x": 1}}
        report = world_snapshot.restore(self.world, snapshot)
        self.assertIn("ghost_region:ghost_room", report.skipped_rooms)
        self.assertIn("ghost_npc", report.skipped_npcs)
        self.assertIn("ghost_region", report.skipped_regions)
