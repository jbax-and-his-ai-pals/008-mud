# tests/singles/test_set_respawn.py
"""The `set_respawn` effect: where the player rises again after dying.

A character's respawn point starts as the story's start and used to stay there, so dying deep in a story put the player
back in its first room (with its opening already over). A story moves the point as it goes.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.dialogue.effects import apply_effects
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


class TestRisingAgain(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world

    def say(self, command):
        return _MARKUP.sub("", chr(10).join(str(e["payload"]) for e in self.server.execute_command(self.sid, command) if e["type"] == "text"))

    def where(self):
        return "%s:%s" % (self.player.current_region_id, self.player.current_room_id)

    def test_it_starts_at_the_story_s_start_and_the_effect_moves_it(self):
        start = (self.world.content_set.start_region_id, self.world.content_set.start_room_id)
        self.assertEqual(start, (self.player.respawn_region_id, self.player.respawn_room_id))
        report = apply_effects({"set_respawn": {"region": "varenholt", "room": "castle_gate"}}, {"player": self.player, "world": self.world})
        self.assertFalse(report.failed)
        self.assertEqual(("varenholt", "castle_gate"), (self.player.respawn_region_id, self.player.respawn_room_id))

    def test_dying_and_respawning_returns_the_player_there(self):
        apply_effects({"set_respawn": {"region": "varenholt", "room": "castle_gate"}}, {"player": self.player, "world": self.world})
        self.player.current_region_id, self.player.current_room_id = "fogreach", "crystal_pool"
        self.player.take_damage(10 ** 6, "physical")
        self.assertFalse(self.player.is_alive)
        self.say("respawn")
        self.assertTrue(self.player.is_alive)
        self.assertEqual("varenholt:castle_gate", self.where())

    def test_a_room_that_is_not_there_is_refused_and_nothing_changes(self):
        before = (self.player.respawn_region_id, self.player.respawn_room_id)
        report = apply_effects({"set_respawn": {"region": "varenholt", "room": "no_such_room"}}, {"player": self.player, "world": self.world})
        self.assertTrue([f for f in report.failed if "set_respawn" in f])
        self.assertEqual(before, (self.player.respawn_region_id, self.player.respawn_room_id))

    def test_it_is_saved_with_the_character(self):
        apply_effects({"set_respawn": {"region": "varenholt", "room": "castle_gate"}}, {"player": self.player, "world": self.world})
        saved = self.player.to_dict(self.world)
        self.assertEqual(("varenholt", "castle_gate"), (saved["respawn_region_id"], saved["respawn_room_id"]))


class TestTheValidator(unittest.TestCase):
    def problems(self, effect):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, package)
        (package / "data" / "scenes").mkdir(exist_ok=True)
        (package / "data" / "scenes" / "respawn.json").write_text(json.dumps({"s": {"beats": [{"text": "x", "effects": effect}]}}), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(package) if i.severity == "error"]

    def test_a_good_room_is_accepted(self):
        self.assertEqual([], [m for m in self.problems({"set_respawn": {"region": "varenholt", "room": "castle_gate"}}) if "set_respawn" in m])

    def test_a_missing_room_and_a_missing_field_are_refused(self):
        self.assertTrue([m for m in self.problems({"set_respawn": {"region": "varenholt", "room": "nowhere"}}) if "set_respawn" in m])
        self.assertTrue([m for m in self.problems({"set_respawn": {"region": "varenholt"}}) if "room" in m])


if __name__ == "__main__":
    unittest.main()
