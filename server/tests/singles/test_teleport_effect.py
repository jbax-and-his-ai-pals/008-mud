# tests/singles/test_teleport_effect.py
"""A conversation or an item can send the player somewhere.

`teleport` moves the player with `World._arrive` (the half of `change_room` that puts a
player in a room and says what they see) and without `_evaluate_exit_gate`: a warp does
not walk through a door, so a lock on the way in does not stop it. It runs last in the
effect order, so the rest of the effect (a message, a reward) is delivered where the
player *was*, and the arrival is what they read at the end. A chain of arrivals that each
send the player on is capped (three), because a loop must not hang the server.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.dialogue.effects import KNOWN_EFFECTS, apply_effects
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


class _Warp(GameTestBase):
    def apply(self, effects):
        return apply_effects(effects, {"player": self.player, "world": self.world})

    def elsewhere(self):
        """(region, room) of a room other than the player's, in another region."""
        for region_id, region in self.world.regions.items():
            if region_id != self.player.current_region_id and region.rooms:
                return region_id, sorted(region.rooms)[0]
        self.fail("no other region")

    def where(self):
        return self.player.current_region_id, self.player.current_room_id


class TestTheVocabulary(unittest.TestCase):
    def test_teleport_is_known(self):
        self.assertIn("teleport", KNOWN_EFFECTS)


class TestTeleporting(_Warp):
    def test_the_player_arrives(self):
        region, room = self.elsewhere()
        report = self.apply({"teleport": {"region": region, "room": room}})
        self.assertEqual((region, room), self.where())
        self.assertTrue(report.applied, report.summary())

    def test_the_room_is_marked_visited_and_described(self):
        region, room = self.elsewhere()
        target = self.world.get_region(region).get_room(room)
        target.visited = False
        report = self.apply({"teleport": {"region": region, "room": room}})
        self.assertTrue(target.visited)
        self.assertIn(target.name.upper(), report.message(), "the player is told where they are")

    def test_a_new_region_is_announced(self):
        region, room = self.elsewhere()
        self.assertIn("You have entered", self.apply({"teleport": {"region": region, "room": room}}).message())

    def test_it_runs_last_so_the_rest_is_delivered_before_the_arrival(self):
        region, room = self.elsewhere()
        self.player.runtime_state.gold = 0
        report = self.apply({"teleport": {"region": region, "room": room}, "give_gold": 7, "message": "The light takes you."})
        self.assertEqual(7, self.player.runtime_state.gold)
        text = report.message()
        self.assertLess(text.index("The light takes you."), text.index("You have entered"))

    def test_it_does_not_walk_through_the_door_so_a_lock_does_not_stop_it(self):
        region, room = self.elsewhere()
        self.world.get_region(region).get_room(room).properties["locked_by"] = "item_nobody_has"
        self.apply({"teleport": {"region": region, "room": room}})
        self.assertEqual((region, room), self.where())

    def test_a_room_that_does_not_exist_is_reported_and_the_player_stays(self):
        origin = self.where()
        report = self.apply({"teleport": {"region": "nowhere", "room": "nothing"}})
        self.assertTrue(any("teleport" in f for f in report.failed), report.summary())
        self.assertEqual(origin, self.where())

    def test_a_chain_of_arrivals_that_each_send_the_player_on_is_cut_off_at_three(self):
        region, room = self.elsewhere()
        calls = []
        real = self.world._arrive

        def arrive_and_send_on(player, new_region, new_room, old_region):
            calls.append(new_room)
            text = real(player, new_region, new_room, old_region)
            self.world.teleport_player(player, region, room)   # every arrival sends the player on again
            return text

        with mock.patch.object(self.world, "_arrive", side_effect=arrive_and_send_on):
            self.apply({"teleport": {"region": region, "room": room}})
        self.assertEqual(3, len(calls), "the chain stops at the cap instead of looping")
        self.assertEqual(0, self.world._teleport_depth, "and the depth is released afterwards")

    def test_a_dead_player_is_not_sent_anywhere(self):
        region, room = self.elsewhere()
        origin = self.where()
        self.player.is_alive = False
        report = self.apply({"teleport": {"region": region, "room": room}})
        self.assertEqual(origin, self.where())
        self.assertTrue(report.failed, report.summary())


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice, changing only its hermit's conversation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.graph = self.package / "data" / "dialogue" / "hermit_gift.json"

    def _errors(self, effects):
        payload = json.loads(self.graph.read_text(encoding="utf-8"))
        payload["nodes"]["greeting"]["choices"][0]["effects"] = effects
        self.graph.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error" and "hermit_gift" in i.message]

    def test_a_good_teleport_is_accepted(self):
        self.assertEqual([], self._errors({"teleport": {"region": "caves", "room": "fairy_pool"}}))

    def test_a_region_or_room_nobody_authored_is_refused(self):
        errors = self._errors({"teleport": {"region": "nowhere", "room": "fairy_pool"}})
        self.assertTrue(any("nowhere" in m for m in errors), errors)
        errors = self._errors({"teleport": {"region": "caves", "room": "no_such_room"}})
        self.assertTrue(any("no_such_room" in m for m in errors), errors)

    def test_both_a_region_and_a_room_are_needed(self):
        for effect in ({"region": "caves"}, {"room": "fairy_pool"}, {}):
            errors = self._errors({"teleport": effect})
            self.assertTrue(any("teleport" in m for m in errors), (effect, errors))


if __name__ == "__main__":
    unittest.main()
