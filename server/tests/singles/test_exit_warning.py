# tests/singles/test_exit_warning.py
"""An exit that warns once: `exit_requirements` of type `warning`.

The first attempt to go that way is refused and the warning told (a scene, so it can be slow); the second goes
through. It is remembered on the player, so a second character meets the warning again, and it is checked by the
content validator like the other requirement types.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)
WARNING = {"type": "warning", "scene": "the_warning", "failure_message": "You start east, and stop."}
SCENES = {"the_warning": {"lock": False, "beats": [
    {"after": 2, "text": "A voice in the stone: turn back."},
    {"after": 2, "text": "Last chance."},
]}}


def _package(requirement):
    tmp = Path(tempfile.mkdtemp())
    package = tmp / "story_fixture"
    shutil.copytree(STORY_FIXTURE, package)
    (package / "data" / "scenes").mkdir(exist_ok=True)
    (package / "data" / "scenes" / "warning.json").write_text(json.dumps(SCENES), encoding="utf-8")
    path = package / "data" / "regions" / "varenholt.json"
    region = json.loads(path.read_text(encoding="utf-8"))
    properties = region["rooms"]["castle_gate"].setdefault("properties", {})
    properties.setdefault("exit_requirements", {})["east"] = requirement
    path.write_text(json.dumps(region), encoding="utf-8")
    return tmp, package


class TestTheFirstTryIsWarned(unittest.TestCase):
    def setUp(self):
        tmp, package = _package(WARNING)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(package), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.player.current_region_id, self.player.current_room_id = "varenholt", "castle_gate"

    def say(self, command):
        return _MARKUP.sub("", NL.join(str(e["payload"]) for e in self.server.execute_command(self.sid, command) if e["type"] == "text"))

    def tick(self, seconds):
        told = []
        for _ in range(seconds):
            self.server.world.clock.advance(1.0)
            told += [str(e["payload"]) for e in self.server.tick(self.sid) + self.server._flush_background_batch(self.sid) if e["type"] == "text"]
        return _MARKUP.sub("", NL.join(told))

    def where(self):
        return "%s:%s" % (self.player.current_region_id, self.player.current_room_id)

    def test_the_first_attempt_is_refused_and_the_warning_told_slowly(self):
        self.assertIn("You start east, and stop.", self.say("go east"))
        self.assertEqual("varenholt:castle_gate", self.where())
        self.assertNotIn("turn back", self.say("look"), "the warning is not blurted at once")
        told = self.tick(8)
        self.assertIn("A voice in the stone: turn back.", told)
        self.assertIn("Last chance.", told)

    def test_the_second_attempt_goes_through(self):
        self.say("go east")
        self.say("go east")
        self.assertEqual("varenholt:stores", self.where())

    def test_and_the_third_and_every_later_one_without_a_warning(self):
        self.say("go east")
        self.tick(8)   # the warning has been told
        self.say("go east")
        self.say("go west")
        said = self.say("go east")
        self.assertEqual("varenholt:stores", self.where())
        self.assertNotIn("You start east", said)
        self.assertNotIn("turn back", self.tick(8))

    def test_it_is_remembered_on_the_player_so_a_saved_character_is_not_warned_twice(self):
        self.say("go east")
        self.assertTrue(self.player.flags.get("exit_warned:varenholt:castle_gate:east"))

    def test_a_warning_with_only_a_message_still_stops_the_first_try(self):
        tmp, package = _package({"type": "warning", "failure_message": "Mind the step."})
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        server = HeadlessServer(db_path=":memory:", content_set_path=str(package), deterministic_test_mode=True,
                                default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="hero").session_id
        server.execute_command(sid, "char create Aldric")
        player = server.get_player_for_session(sid)
        player.current_region_id, player.current_room_id = "varenholt", "castle_gate"
        said = lambda c: NL.join(str(e["payload"]) for e in server.execute_command(sid, c) if e["type"] == "text")
        self.assertIn("Mind the step.", said("go east"))
        self.assertEqual("castle_gate", player.current_room_id)
        said("go east")
        self.assertEqual("stores", player.current_room_id)


class TestTheValidatorChecksIt(unittest.TestCase):
    def problems(self, requirement):
        tmp, package = _package(requirement)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        issues = content_set.validate_content_set(package)
        return [i.message for i in issues if i.severity == "error"]

    def test_a_scene_that_does_not_exist_is_refused(self):
        found = self.problems({"type": "warning", "scene": "no_such_scene"})
        self.assertTrue([m for m in found if "no_such_scene" in m], found)

    def test_a_warning_with_nothing_to_say_is_refused(self):
        found = self.problems({"type": "warning"})
        self.assertTrue([m for m in found if "needs a scene or a failure_message" in m], found)

    def test_an_unknown_key_is_refused(self):
        found = self.problems({"type": "warning", "scene": "the_warning", "consume": True})
        self.assertTrue([m for m in found if "consume" in m], found)

    def test_a_good_one_is_accepted(self):
        self.assertEqual([], [m for m in self.problems(WARNING) if "castle_gate" in m])


if __name__ == "__main__":
    unittest.main()
